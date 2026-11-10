"""US Stock Strategy Lab — public demonstration with gated owner workspace.

Guest mode does not register or execute any private database-enabled pages.
The owner signs in with the existing PBKDF2 credentials from Streamlit Secrets.
"""
import hashlib
import hmac
import streamlit as st

st.set_page_config(page_title="US Stock Strategy Lab", page_icon="📈", layout="wide")


def login_config():
    try:
        return st.secrets["local_login"]
    except (KeyError, FileNotFoundError):
        return None


def verify_password(password, config):
    if config is None:
        return False
    try:
        salt = bytes.fromhex(config["salt"])
        expected = bytes.fromhex(config["password_hash"])
        iterations = int(config["iterations"])
        if len(salt) != 32 or len(expected) != 32 or iterations < 600_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def reset_session():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def sign_in():
    st.title("Owner sign in")
    st.write("Private AI backtests, saved strategies and Telegram records are restricted to the owner.")
    config = login_config()
    if config is None:
        st.error("Owner login is not configured.")
        st.stop()
    if st.session_state.get("_owner_login_blocked", False):
        st.error("Too many failed attempts in this session. Close this browser session before trying again.")
        return
    with st.form("owner_login_form"):
        password = st.text_input("Owner password", type="password")
        submit = st.form_submit_button("Sign in", type="primary")
    if submit:
        if verify_password(password, config):
            st.session_state["_lab_authenticated"] = True
            st.session_state["_lab_login_failures"] = 0
            st.rerun()
        count = st.session_state.get("_lab_login_failures", 0) + 1
        st.session_state["_lab_login_failures"] = count
        if count >= 5:
            st.session_state["_owner_login_blocked"] = True
            st.error("Too many failed attempts in this session.")
        else:
            st.error("Incorrect password.")


def private_cloud_page():
    from cloud_view import main
    main()


if st.session_state.get("_lab_authenticated", False):
    home = st.Page("web_app.py", title="Owner workspace", icon="📊", default=True)
    cloud = st.Page(private_cloud_page, title="Private cloud records", icon="☁️", url_path="cloud")
    page = st.navigation([home, cloud], position="hidden")
    with st.sidebar:
        st.caption("🔒 Owner access")
        st.page_link(home, label="📊 Owner workspace", use_container_width=True)
        st.page_link(cloud, label="☁️ Private cloud records", use_container_width=True)
        if st.button("Sign out and return to demo", use_container_width=True):
            reset_session()
        st.divider()
    page.run()
else:
    guest = st.Page("web_app.py", title="Full guest workspace", icon="🌐", default=True)
    owner = st.Page(sign_in, title="Owner sign in", icon="🔐", url_path="owner")
    page = st.navigation([guest, owner], position="hidden")
    with st.sidebar:
        st.caption("🌐 Public portfolio showcase")
        st.page_link(guest, label="Try the full application", use_container_width=True)
        st.page_link(owner, label="Owner sign in", use_container_width=True)
        st.divider()
        st.caption("Guests can use AI, backtesting, comparisons and analytics. Owner cloud and Telegram records remain private.")
    page.run()
