#!/bin/bash

ROOT_DIR="${1:-.}"  # Pass directory as argument, defaults to current

for dir in "$ROOT_DIR"/*/; do
    echo "================================"
    echo "Directory: $dir"

    # Find the latest end date in this directory
    latest=$(ls "$dir"*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json 2>/dev/null | grep -oP '\d{4}-\d{2}-\d{2}(?=\.json)' | sort | tail -n 1)

    if [ -z "$latest" ]; then
        echo "No matching files found, skipping."
        continue
    fi

    echo "Files to KEEP (latest date: $latest):"
    ls "$dir"*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json | grep "_${latest}.json" | sed 's|.*/||'

    to_delete=$(ls "$dir"*_[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json | grep -v "_${latest}.json")

    if [ -z "$to_delete" ]; then
        echo "Nothing to delete."
        continue
    fi

    echo ""
    read -p "Delete old files? [y/n] " answer
    if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
        echo "$to_delete" | xargs rm -f
        echo "Deleted."
    else
        echo "Skipped."
    fi

    echo ""
done
