import json
import boto3
import os
import psycopg2
import pandas as pd
from botocore.exceptions import ClientError

def get_secret(secret_name):
    region_name = "eu-west-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    return secret['username'], secret['password']

def handler(event, context):
    # Connect to S3
    s3 = boto3.client('s3')
    bucket = os.environ['BUCKET']
    
    # Get the object from the event
    key = event['Records'][0]['s3']['object']['key']
    file_name = key.split('/')[-1]
    
    # Download the file
    tmp_file = f'/tmp/{file_name}'
    s3.download_file(bucket, key, tmp_file)
    
    # Read the CSV file into a DataFrame
    df = pd.read_csv(tmp_file)
    
    # Determine the table name based on the file name
    if 'customer' in file_name:
        table_name = 'customers'
        #CustomerID,Name,Address,Phone,Email
        create_table_query = """
        CREATE TABLE IF NOT EXISTS customers (
            CustomerID SERIAL PRIMARY KEY,
            Name VARCHAR(100),
            Address VARCHAR(100),
            Phone VARCHAR(20),
            Email VARCHAR(100)
        )
        """
    elif 'project' in file_name:
        table_name = 'projects'
        #ProjectID,ProjectName,StartDate,EndDate,Status
        create_table_query = """
        CREATE TABLE IF NOT EXISTS projects (
            ProjectID SERIAL PRIMARY KEY,
            ProjectName VARCHAR(100),
            StartDate DATE,
            EndDate DATE,
            Status VARCHAR(50)
        )
        """
    elif 'maintenance' in file_name:
        table_name = 'maintenance_reports'
        # ReportID,ProjectID,Date,Description,Technician
        create_table_query = """
        CREATE TABLE IF NOT EXISTS maintenance_reports (
            ReportID SERIAL PRIMARY KEY,
            ProjectID INT,
            Date DATE,
            Description TEXT,
            Technician VARCHAR(100)
        )
        """
    else:
        return {
            'statusCode': 400,
            'body': json.dumps('Invalid file name')
        }
    
    username, password = get_secret(os.environ['SECRET'])
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        dbname=os.environ['DB_NAME'],
        user=username,
        password=password,
        host=os.environ['DB_HOST'],
        port=os.environ['DB_PORT']
    )
    
    cur = conn.cursor()
    
    # Create the table if it does not exist
    cur.execute(create_table_query)
    
    # Insert data into the table
    for _, row in df.iterrows():
        columns = ', '.join(row.index)
        values = ', '.join(f"'{str(x)}'" for x in row.values)
        insert_query = f"INSERT INTO {table_name} ({columns}) VALUES ({values})"
        cur.execute(insert_query)
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {
        'statusCode': 200,
        'body': json.dumps('Success')
    }
