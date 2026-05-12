# Grafana Dashboards

## Overview

This repository also includes Grafana dashboards for visualizing the data processed by the Python scripts and stored in InfluxDB.

Currently:
- The FERS dashboard is fully completed and operational
- The Digitiser dashboard is still under development


# Importing Dashboards into Grafana

## 1. Open Grafana

Start Grafana and log into your account.


## 2. Go to the Import Section

In the left-side menu:

Home → Dashboards → Import


## 3. Import the Dashboard JSON File

You can import a dashboard in two ways:

### Option 1: Upload JSON file

- Click "Upload dashboard JSON file"
- Select the dashboard file from this repository


### Option 2: Copy and paste JSON content

- Open the JSON dashboard file
- Copy its contents
- Paste it into the Grafana import window


## 4. Configure the Data Source

During the import process, Grafana will ask for the InfluxDB data source.

Select the correct InfluxDB source configured in your Grafana instance.


## 5. Finish Import

Click "Import" and the dashboard will be available in Grafana.


# Dashboard Status


## FERS Dashboard

The FERS dashboard is fully completed and operational.

It includes:
- Run monitoring
- Data visualization
- Metrics display
- Real-time updates from InfluxDB


## Digitiser Dashboard

The Digitiser dashboard is currently still in development.

Some panels or functionalities may be incomplete or subject to future changes.


# Important Notes

If you modify:
- The InfluxDB organization
- Bucket
- Token
- Measurement names

you may also need to update:
- Grafana data source configuration
- Dashboard queries
- Variable definitions inside the dashboard


# Recommended Setup

1. Configure InfluxDB as a Grafana data source
2. Import the dashboards
3. Verify that the bucket and organization names match your configuration
4. Start the Python monitoring scripts
5. Open the dashboards to monitor incoming data in real time
