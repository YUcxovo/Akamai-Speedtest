# Akamai Server Based Speed Test CLI

Command line interface for network speed test, based on [Akamai](https://www.linode.com/) Servers.

Akamai's [online netspeed test website](https://www.linode.com/speed-test/)

## Requirements

Python version >= 3.7

## Installation

### pip
`pip install akamai-speedtest`

### Github
`pip install git+https://github.com/YUcxovo/Akamai-Speedtest.git`

## Features

- IP test
- Ping test (ping, jitter, packet loss)
- Download speed, single stream and multi-stream
- Upload speed, single stream and multi-stream
- Current network situation monitor (send and receive)

## Usage

### Basic Usage
Simply typing `speedtest` in terminal, the most suitable server will be automatically chosen. Then ip test, ping test, multi-stream download and upload test will start in turn.

### Use with Commands

- `speedtest [Options]`
- `speedtest ip`
- `speedtest ping [Optional: url] [Options]` 
- `speedtest download [Options]`
- `speedtest upload [Options]`
- `speedtest monitor [Options]`
  
### Custom Settings

A `.json` file including:
- server
- prev_server
- ping_test_times
- ping_wait_time
- download_multitest
- upload_multitest
- multi_download_max_time
- multi_upload_max_time
- single_download_max_time
- single_upload_max_time
- auto_time_reduce
- download_gracetime
- upload_gracetime
- download_max_stream
- upload_max_stream
- download_multistream_delay
- upload_multistream_delay
- download_update_interval
- upload_update_interval
- multi_download_package_size
- multi_upload_package_size
- single_download_package_size
- single_upload_package_size
- download_chunk_size
- upload_chunk_size
- overhead_compensation_factor

Use the custom settings by default by setting environment variable `AKM_SPEEDTEST_SETTINGS` as the path of settings file.

## Attributions

This application uses services from:
- [ipify API](https://www.ipify.org/) for ip test
- Akamai Technologies, Inc. for download and upload test
