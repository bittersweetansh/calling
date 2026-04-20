import streamlit as st
import requests

API = "http://127.0.0.1:8000"

st.title("Appointment Dashboard (No AI)")

if st.button("Refresh"):
    data = requests.get(f"{API}/appointments").json()
    st.write(data)

st.subheader("Book Appointment")
name = st.text_input("Name")
address = st.text_input("Address")
time_text = st.text_input("Time (e.g. tomorrow 10am)")

if st.button("Book"):
    res = requests.post(f"{API}/schedule", json={
        "name": name,
        "address": address,
        "natural_time": time_text
    })
    st.write(res.json())