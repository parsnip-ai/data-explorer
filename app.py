import streamlit as st
import hickle as hkl
import pandas as pd
import json
from google.cloud import firestore
from google.oauth2 import service_account
from pathlib import Path
from toolz import dicttoolz as dz
from toolz import itertoolz as it
import altair as alt

# Secret usage in streamlit deploy: https://blog.streamlit.io/streamlit-firestore-continued/

# Streamlit config
title = "Quick User Data Explorer"
st.set_page_config(page_title=title)
st.title(title)
dev = False


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


def pull_latest_data(db, dev=False):
    """
    Pulls latest user data collection from firestore

    Args:
        db (firestore.Client): firestore client connection
        dev (bool; optional): if True saves firestore data to csv locally so development doesn't incur uneccesary reads

    Returns:
        dict/Box: dictionary of user collection
    """

    if dev and Path("user_data.hkl").exists():
        print("Loading saved data")
        return hkl.load("user_data.hkl")

    users_ref = db.collection("users")
    user_data = dict()

    for user in users_ref.stream():
        doc = user.to_dict()
        user_data[doc["uid"]] = doc

    if dev:
        print("Saving data to limit reads during development")
        hkl.dump(user_data, "user_data.hkl", mode="w")

    return user_data


def anonymize_to_df(user_data):
    """Convert user data nested dict to dataframe and drop identifying info"""
    df = (
        pd.DataFrame(user_data)
        .T.drop(columns=["name", "email", "uid"])
        .reset_index(drop=True)
    )
    return df


def plot_onboarding(df):
    onboarded = df.onboarded.value_counts()
    st.write("## Number of Onboarded Users")
    st.write(
        "*Users who have gone through or dismissed the onboarding (1=Onboarded; 0=Not)*"
    )
    st.bar_chart(onboarded)


def plot_levels(df):
    levels = df.level.value_counts()
    st.write("## Number of users at each level")
    st.write("*FYI I'm the (outlier) highest level user*")
    st.bar_chart(levels)


def plot_feedback(df):
    feedback = (~df.providedFeedback.isnull()).value_counts()
    st.write("## Number of users who've provided feedback")
    st.write("*Sent us at least one form of feedback (1=Yes; 0=No)*")
    st.bar_chart(feedback)


def plot_cooked_or_viewed_recipes(df):
    """Plots number of users who've never cooked, completed at least 1 recipe, or completed no recipes but have 1 in progress"""

    def get_user_recipe_status(d):

        if d == {}:
            return "Never entered cook mode"
        if not any(dz.valmap(lambda d: d.get("cookedBefore"), d).values()) and any(
            dz.valmap(lambda d: d.get("inprogress"), d).values()
        ):
            return "Recipe in progress, but never completed any"
        if any(dz.valmap(lambda d: d.get("cookedBefore"), d).values()):
            return "Completed at least 1 recipe"

    recipe_statuses = df.recipes.apply(get_user_recipe_status).value_counts()
    st.write("## User Recipe Status")
    st.write(
        "*We don't know if they've actually cooked it. Just that they went through the entirety of cook mode.*"
    )
    st.bar_chart(recipe_statuses)


def plot_num_completed_recipes(df):
    def count_recipes(d):
        if d == {}:
            return 0
        return sum(dz.valmap(lambda d: d.get("cookedBefore", False), d).values())

    recipe_counts = df.recipes.apply(count_recipes).value_counts().drop(0, axis=0)
    st.write("## Number of Completed Recipes")
    st.write(
        "*Just counting from the subset of users who've completed at least 1 recipe*"
    )
    st.bar_chart(recipe_counts)


def plot_cooked_or_viewed_skills(df):
    """Plots number of users who've never cooked, completed at least 1 recipe, or completed no recipes but have 1 in progress"""

    def get_user_skill_status(d):

        if d == {}:
            return "Never saw a skill"
        return "Saw at least 1 skill"

    skill_statuses = df.skills.apply(get_user_skill_status).value_counts()
    st.write("## User Skill Status")
    st.write("*In other words have at least 1 skill at level 1*")
    st.bar_chart(skill_statuses)


def plot_skill_hist(df):
    skill_levels = df.skills.apply(
        lambda d: list(dz.valmap(lambda d: d.get("score"), d).values())
    )
    skill_counts = it.frequencies(list(it.concat(skill_levels.to_list())))
    num_skills = sum(skill_counts.values())
    st.write("## User Skill Levels")
    st.write("*Proportion of skills at each level across all users' skills*")
    st.bar_chart(
        pd.DataFrame(dz.valmap(lambda v: v / num_skills, skill_counts), index=[0]).T
    )


def plot_signups(df):
    sign_ups = (
        df.assign(counter=1)
        .set_index("creationDate")
        .sort_index()
        .counter.cumsum()
        .reset_index()
    )
    # st.line_chart(sign_ups)
    c = (
        alt.Chart(sign_ups)
        .mark_line()
        .encode(
            x=alt.X("creationDate:T", title="Sign Up Date"),
            y=alt.Y("counter:Q", title="Cumulative # of Users"),
            tooltip=["counter", "creationDate"],
        )
    )
    st.write("## User Sign Ups")
    st.write("*Cumulative account creations over time*")
    st.altair_chart(c, use_container_width=True)


def most_popular_recipes(df, db):

    st.write("## Most Popular Recipes")
    st.write("*Number of users who started/completed each recipe*")
    st.write("Mouse over any bar to see full recipe name")

    recipe_counts = it.frequencies(
        it.concat(df.recipes.apply(lambda d: list(d.keys())).to_list())
    )
    recipe_names = []
    for recipe_id in recipe_counts.keys():
        recipe_ref = db.collection("fl_content").document(recipe_id)
        recipe_doc = recipe_ref.get()
        recipe_names.append(recipe_doc.get("name"))
    recipe_counts = dict(zip(recipe_names, recipe_counts.values()))
    recipe_counts = (
        pd.DataFrame(recipe_counts, index=["count"])
        .T.reset_index()
        .rename(columns={"index": "recipe"})
        .sort_values(by="count")
    )
    c = (
        alt.Chart(recipe_counts)
        .mark_bar()
        .encode(x=alt.X("recipe:N", sort="-y"), y="count", tooltip=["count", "recipe"])
    )
    st.altair_chart(c, use_container_width=True)


def most_popular_skills(df, db):

    st.write("## Most Popular Skills")
    st.write("*Number of users who have at least 1 level in each skill*")
    st.write("Mouse over any bar to see skill name")

    skill_counts = it.frequencies(
        it.concat(df.skills.apply(lambda d: list(d.keys())).to_list())
    )
    skill_names = []
    for skill_id in skill_counts.keys():
        skill_ref = db.collection("fl_content").document(skill_id)
        skill_doc = skill_ref.get()
        skill_names.append(skill_doc.get("name"))
    skill_counts = dict(zip(skill_names, skill_counts.values()))
    skill_counts = (
        pd.DataFrame(skill_counts, index=["count"])
        .T.reset_index()
        .rename(columns={"index": "skill"})
        .sort_values(by="count")
    )
    c = (
        alt.Chart(skill_counts)
        .mark_bar()
        .encode(
            x=alt.X("skill:N", sort="-y", axis=alt.Axis(labels=False)),
            y="count",
            tooltip=["count", "skill"],
        )
    )
    st.altair_chart(c, use_container_width=True)


# Pull latest data
st.write(
    "**Push the button below to pull the latest user data from the live database. This will grab all the user records we have and generate some plots. You can return to this site at anytime and pressing the button will grab the freshest data we have.**"
)
st.write("*I haven't filtered out any users including the 5 of us, Definery, etc*")
if st.button("Pull Latest Data"):
    with st.spinner("Loading..."):
        db = init_fb_connection()
        user_data = pull_latest_data(db, dev)
        data = anonymize_to_df(user_data)

        st.write("### Number of user records: ", data.shape[0])
        plot_signups(data)
        plot_onboarding(data)
        plot_feedback(data)
        plot_levels(data)
        plot_cooked_or_viewed_recipes(data)
        plot_num_completed_recipes(data)
        plot_cooked_or_viewed_skills(data)
        plot_skill_hist(data)
        most_popular_recipes(data, db)
        most_popular_skills(data, db)
