# README

## Overview

This repository contains several Python scripts used to analyze data from FERS and Digitiser runs/events.

All scripts:
- Send processed data to InfluxDB
- Generate CSV output files
- Require correct local paths configuration


# Requirements

Before running any script, you must create a Python virtual environment (venv) and install the required dependencies.


## 1. Create a virtual environment

python3 -m venv venv


Activate it:

### Linux / macOS

source venv/bin/activate


### Windows

venv\Scripts\activate


## 2. Install required libraries

Install the Python client for InfluxDB:

pip install influxdb-client


## 3. Install tmux

It is strongly recommended to use tmux so the scripts continue running even after closing the terminal session.


### Ubuntu / Debian

sudo apt install tmux


### macOS

brew install tmux


Run a tmux session with:

tmux


Detach from the session without stopping the script:

CTRL + B, then D


Reattach later with:

tmux attach


# Scripts Description


## 1. Fers_script.py

This script is used to analyze the data of a specific FERS Run that you provide manually.

You specify the Run you want to analyze, and the script:
- Reads the corresponding data
- Sends processed information to InfluxDB
- Generates a CSV file with the results


## 2. FERS_Run_search.py + fers_script_OnlineMonitoring.py

These two scripts work together for online monitoring.

Their purpose is to:
- Continuously monitor for new FERS Runs
- Detect when a new Run appears
- Automatically launch the analysis for that Run
- Send results to InfluxDB
- Generate CSV files automatically

These scripts are intended to run continuously, which is why using tmux is highly recommended.


## 3. Digitiser_script.py

This script is used to analyze data from a specific Digitiser event.

You specify the event to analyze, and the script:
- Processes the event data
- Sends the results to InfluxDB
- Generates a CSV output file


# Important Configuration Notes


## InfluxDB Configuration

If you modify any of the following:
- Organization (org)
- Bucket
- Token

you MUST update the configuration in all scripts accordingly.

Otherwise, the scripts will not be able to write data to InfluxDB correctly.


## Paths Configuration

Before running the scripts, make sure to configure:
- The path where the input data is stored
- The destination path where the generated CSV files should be saved

Update these paths directly inside the scripts according to your local environment.


# Recommended Workflow

1. Create and activate the venv
2. Install dependencies
3. Start a tmux session
4. Run the desired script
5. Leave the script running safely in the background


Example:

tmux

source venv/bin/activate

python3 fers_script_OnlineMonitoring.py


Detach from tmux:

CTRL + B, then D


The script will continue running even after closing the terminal.
