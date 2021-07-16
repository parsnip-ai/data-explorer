import streamlit as st
import hickle as hkl
from box import Box
from datetime import date
import json
from google.cloud import firestore
from google.oauth2 import service_account
from pathlib import Path

# Secret usage in streamlit deploy: https://blog.streamlit.io/streamlit-firestore-continued/

# Streamlit config
title = "User Data Explorer"
st.set_page_config(page_title=title)
st.title(title)


def get_local_files():
    """Retrieve a list of the currently available user data .hkl files"""
    data = sorted(Path("data").glob("*.hkl"))
    if data:
        return list(map(lambda x: x.stem, data))
    else:
        return []


def init_fb_connection():
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    db = firestore.Client(credentials=creds, project="parsnip-cms")
    return db


def pull_latest_data(db):
    """
    Pulls and saves the latest user data collection from firestore

    Args:
        db (firestore.Client): firestore client connection

    Returns:
        dict/Box: dictionary of user collection
    """

    users_ref = db.collection("users")
    user_data = dict()

    for user in users_ref.stream():
        doc = user.to_dict()
        user_data[doc["uid"]] = doc

    user_data = Box(user_data)
    today = date.today().strftime("%m-%d-%y")
    # Save user data to a file
    hkl.dump(user_data, f"data/{today}.hkl", mode="w")

    # Update file list
    st.session_state.backups = get_local_files()

    return user_data


# Setup stateful variables
user_data = None
if "backups" not in st.session_state:
    st.session_state.backups = get_local_files()

# Initialize fb connection
db = init_fb_connection()

# File select and load
if st.session_state.backups:
    data_file = st.selectbox(
        "Choose previous user data snapshot to view", st.session_state.backups
    )
    if st.button("Load"):
        user_data = hkl.load(f"data/{data_file}.hkl")
else:
    st.write("No user data snapshots exist")

st.write("Or")

# Pull latest data
if st.button("Pull Latest Data"):
    with st.spinner("Loading..."):
        user_data = pull_latest_data(db)

# Data display
if user_data:
    st.write(user_data)
