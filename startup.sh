#!/bin/bash
echo "Starting Streamlit app on port $PORT..."
streamlit run make_kon2.py --server.port $PORT --server.address 0.0.0.0 --server.enableCORS false

