#!/bin/bash

# Check if we have the required arguments
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <topic> <json_message>"
    exit 1
fi

TOPIC=$1
MESSAGE=$2

# Produce the message to the topic
echo "$MESSAGE" | rpk topic produce "$TOPIC"
