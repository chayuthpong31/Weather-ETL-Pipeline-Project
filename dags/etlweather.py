from airflow import DAG
from airflow.providers.http.hooks.http import HttpHook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.decorators import task
from datetime import datetime, timedelta

# Latitude and longitude for the desired location (London in this case)
LATITUDE = '51.5074'
LONGITUDE = '-0.1278'
POSTGRES_CONN_ID='postgres_default'
API_CONN_ID='open_meteo_api'

start_date = datetime.now() - timedelta(days=1)

default_args={
    'owner':'airflow',
    'start_date':start_date,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

## DAG
with DAG(dag_id='weather_etl_pipeline',
          default_args=default_args,
          schedule='@daily',
          catchup=False) as dags:
    
    @task()
    def extract_weather_data():
        """Extract weather data from Open-Meteo API using Airflow Connection."""

        # Use HTTP Hook to get connection details from Airflow connection
        # HttpHook handles connection pooling and error handling
        ## https://api.open-meteo.com/v1/forecast?latitude=51.5074&longitude=-0.1278&current_weather=true
        http_hook = HttpHook(http_conn_id=API_CONN_ID, method='GET')

        # Build the API endpoint
        endpoint = f'/v1/forecast?latitude={LATITUDE}&longitude={LONGITUDE}&current_weather=true'

        # Make the request via the HTTP Hook. .run() will raise an exception
        # for non-2xx status codes automatically.
        response = http_hook.run(endpoint)
        return response.json()
        
    @task()
    def transform_weather_data(weather_data):
        """Transform the extracted weather data."""
        current_weather = weather_data['current_weather']
        transformed_data = {
            'latitude': float(LATITUDE),
            'longitude': float(LONGITUDE),
            'temperature': float(current_weather['temperature']),
            'windspeed': float(current_weather['windspeed']),
            'winddirection': float(current_weather['winddirection']),
            'weathercode': int(current_weather['weathercode']) # Explicitly cast to int
        }
        return transformed_data
    
    @task()
    def load_weather_data(transformed_data):
        """Load transformed data into PostgreSQL."""
        pg_hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        
        # Use a `try...finally` block to ensure resources are closed
        try:
            conn = pg_hook.get_conn()
            cursor = conn.cursor()

            # Create table if it doesn't exist
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS weather_data (
                latitude FLOAT,
                longitude FLOAT,
                temperature FLOAT,
                windspeed FLOAT,
                winddirection FLOAT,
                weathercode INT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Insert transformed data into the table
            cursor.execute("""
            INSERT INTO weather_data (latitude, longitude, temperature, windspeed, winddirection, weathercode)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                transformed_data['latitude'],
                transformed_data['longitude'],
                transformed_data['temperature'],
                transformed_data['windspeed'],
                transformed_data['winddirection'],
                transformed_data['weathercode']
            ))

            conn.commit()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    ## DAG Worflow- ETL Pipeline
    weather_data = extract_weather_data()
    transformed_data = transform_weather_data(weather_data)
    load_weather_data(transformed_data)