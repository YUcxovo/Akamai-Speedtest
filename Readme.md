# Akamai Server Based Speed Test CLI

Command line interface for network speed test, based on [Akamai](https://www.linode.com/) Servers.

Akamai's [online netspeed test website](https://www.linode.com/speed-test/)

## Requirements

Python version >= 3.7

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

- `speedtest ip`
- `speedtest ping [Optional: url] [Options]` 
- `speedtest download [Options]`
- `speedtest upload [Options]`
- `speedtest monitor [Options]`
  
### Custom Settings

## Attributions

This application uses services from:
- [ipify API](https://www.ipify.org/) for ip test
- Akamai Technologies, Inc. for download and upload test
