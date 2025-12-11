# app.py
import streamlit as st
import pandas as pd
import numpy as np
import json
import time
import threading
import queue
from datetime import datetime, timezone, timedelta
import plotly.graph_objs as go
import paho.mqtt.client as mqtt

# ---------------------------
# CONFIG
# ---------------------------
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
TOPIK_DATA = "smuhsa/gudang/data"
TOPIK_KONTROL = "smuhsa/gudang/kontrol"
TOPIK_STATUS = "smuhsa/gudang/status"

TZ = timezone(timedelta(hours=7))

GLOBAL_QUEUE = queue.Queue()

# ---------------------------
# STREAMLIT SETUP
# ---------------------------
st.set_page_config(page_title="IoT Smart Gudang", layout="wide")
st.title("📦 IoT Smart Gudang — Realtime Dashboard")

if "connected" not in st.session_state:
    st.session_state.connected = False
if "logs" not in st.session_state:
    st.session_state.logs = []
if "last" not in st.session_state:
    st.session_state.last = {}

# ---------------------------
# MQTT CALLBACKS
# ---------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        GLOBAL_QUEUE.put({"_type": "status", "connected": True})
        client.subscribe(TOPIK_DATA)
    else:
        GLOBAL_QUEUE.put({"_type": "status", "connected": False})

def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    try:
        data = json.loads(payload)
    except:
        data = {"raw": payload}
    GLOBAL_QUEUE.put({"_type": "sensor", "data": data, "ts": time.time()})

# ---------------------------
# MQTT THREAD
# ---------------------------
def start_mqtt_thread():
    def worker():
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    threading.Thread(target=worker, daemon=True).start()

start_mqtt_thread()

# ---------------------------
# PROCESS QUEUE
# ---------------------------
def process_queue():
    while not GLOBAL_QUEUE.empty():
        item = GLOBAL_QUEUE.get()
        ttype = item["_type"]
        if ttype == "status":
            st.session_state.connected = item["connected"]
        elif ttype == "sensor":
            d = item["data"]
            d["ts"] = datetime.fromtimestamp(item["ts"], TZ).strftime("%H:%M:%S")
            st.session_state.last = d
            st.session_state.logs.append(d)
            if len(st.session_state.logs) > 2000:
                st.session_state.logs = st.session_state.logs[-2000:]

process_queue()

# ---------------------------
# UI
# ---------------------------
left, right = st.columns([1,2])

with left:
    st.subheader("Connection Status")
    st.metric("MQTT Connected", "YES" if st.session_state.connected else "NO")
    
    st.markdown("---")
    st.subheader("Last Data")
    last = st.session_state.last
    if last:
        st.json(last)
    else:
        st.info("Menunggu data...")

    st.markdown("---")
    st.subheader("LED Control")
    col1, col2 = st.columns(2)
    if col1.button("LED ON"):
        pub = mqtt.Client()
        pub.connect(MQTT_BROKER, MQTT_PORT, 60)
        pub.publish(TOPIK_KONTROL, "ALERT_ON")
        pub.disconnect()
        st.success("LED ON dikirim")
    if col2.button("LED OFF"):
        pub = mqtt.Client()
        pub.connect(MQTT_BROKER, MQTT_PORT, 60)
        pub.publish(TOPIK_KONTROL, "ALERT_OFF")
        pub.disconnect()
        st.success("LED OFF dikirim")

    st.markdown("---")
    st.subheader("Download Logs")
    if st.button("Download CSV"):
        if st.session_state.logs:
            df = pd.DataFrame(st.session_state.logs)
            csv = df.to_csv(index=False).encode()
            st.download_button("Download CSV", csv, "log_gudang.csv")
        else:
            st.info("Belum ada data")

with right:
    st.subheader("Live Chart")
    df = pd.DataFrame(st.session_state.logs[-200:])
    if not df.empty and "suhu" in df.columns:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["ts"], y=df["suhu"], mode="lines+markers", name="Suhu"))
        if "ldr" in df.columns:
            fig.add_trace(go.Scatter(x=df["ts"], y=df["ldr"], mode="lines+markers", name="LDR", yaxis="y2"))
        fig.update_layout(
            height=500,
            yaxis=dict(title="Suhu"),
            yaxis2=dict(title="LDR", overlaying="y", side="right")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Menunggu data sensor...")
