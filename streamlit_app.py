import streamlit as st
import requests
import uuid
import hashlib
import smtplib
from datetime import datetime

st.set_page_config(page_title="QueryBridge AI", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif; }

/* ── Auth pages ── */
.auth-card {
    max-width: 400px;
    margin: 50px auto;
    padding: 40px 36px;
    background: #fff;
    border: 1px solid #e5e5e5;
    border-radius: 16px;
    box-shadow: 0 4px 32px rgba(0,0,0,.08);
}

/* Override streamlit inputs on auth page */
.auth-wrap .stTextInput input {
    border: 1px solid #e0e0e0 !important;
    border-radius: 9px !important;
    padding: 10px 14px !important;
    font-size: 14px !important;
    background: #fafafa !important;
    color: #111 !important;
    transition: border .2s;
}
.auth-wrap .stTextInput input:focus {
    border-color: #6366f1 !important;
    background: #fff !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,.1) !important;
}
.auth-wrap label { color: #444 !important; font-size: 13px !important; font-weight: 500 !important; }

/* Primary button */
.primary-btn .stButton > button {
    all: unset;
    display: block; width: 100%;
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: #fff !important; font-size: 14.5px !important; font-weight: 600 !important;
    padding: 12px !important; border-radius: 10px !important;
    text-align: center !important; cursor: pointer !important;
    transition: opacity .2s !important; box-sizing: border-box !important;
}
.primary-btn .stButton > button:hover { opacity: .88 !important; }

/* Link-style button */
.link-btn .stButton > button {
    all: unset; color: #6366f1 !important; font-size: 13.5px !important;
    cursor: pointer !important; text-decoration: underline !important;
}
.link-btn .stButton > button:hover { color: #4f46e5 !important; }

/* Divider text */
.or-divider {
    display: flex; align-items: center; gap: 12px;
    color: #bbb; font-size: 12px; margin: 18px 0;
}
.or-divider::before, .or-divider::after {
    content: ''; flex: 1; height: 1px; background: #e8e8e8;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] { background-color: #0f0f0f !important; border-right: 1px solid #1e1e1e; }
[data-testid="stSidebar"] hr { border-color: #1e1e1e !important; margin: 6px 0 !important; }
[data-testid="stSidebar"] label { color: #555 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing:.07em; font-weight:600; }

[data-testid="stSidebar"] .stButton > button {
    all: unset; display: block; width: 100%; padding: 8px 12px;
    border-radius: 8px; font-size: 13.5px; color: #c8c8c8; cursor: pointer;
    transition: background .15s, color .15s; box-sizing: border-box;
    text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
[data-testid="stSidebar"] .stButton > button:hover { background: #1e1e1e !important; color: #fff; }

.menu-col .stButton > button { padding: 6px 10px !important; text-align: center !important; font-size: 16px !important; color: #444 !important; }
.menu-col .stButton > button:hover { color: #aaa !important; background: #2a2a2a !important; }

.ctx-rename .stButton > button { background: #1e1e1e !important; color: #d1d1d1 !important; border-radius: 8px !important; padding: 9px 13px !important; font-size: 13.5px !important; margin-bottom: 2px !important; }
.ctx-rename .stButton > button:hover { background: #2a2a2a !important; color: #fff !important; }
.ctx-delete .stButton > button { background: #1e1e1e !important; color: #f55 !important; border-radius: 8px !important; padding: 9px 13px !important; font-size: 13.5px !important; margin-bottom: 2px !important; }
.ctx-delete .stButton > button:hover { background: #2a1515 !important; }
.ctx-cancel .stButton > button { background: transparent !important; color: #555 !important; border-radius: 8px !important; padding: 6px 13px !important; font-size: 12px !important; }
.save-btn .stButton > button { background: #6366f1 !important; color: #fff !important; border-radius: 7px !important; padding: 7px 12px !important; font-size: 13px !important; font-weight: 500 !important; }
.cancel-btn .stButton > button { background: #1e1e1e !important; color: #888 !important; border-radius: 7px !important; padding: 7px 12px !important; font-size: 13px !important; }

.ctx-box { background: #1c1c1c; border: 1px solid #2e2e2e; border-radius: 10px; padding: 5px; margin: 2px 6px 6px 6px; box-shadow: 0 8px 24px rgba(0,0,0,.5); }
.user-menu-box { background: #1c1c1c; border: 1px solid #2e2e2e; border-radius: 10px; padding: 5px; margin: 4px 6px; box-shadow: 0 -8px 24px rgba(0,0,0,.5); }
.user-menu-box .stButton > button { color: #d1d1d1 !important; padding: 9px 13px !important; font-size: 13.5px !important; background: transparent !important; border-radius: 8px !important; }
.user-menu-box .stButton > button:hover { background: #2a2a2a !important; color: #fff !important; }
.logout-btn .stButton > button { color: #f55 !important; padding: 9px 13px !important; font-size: 13.5px !important; background: transparent !important; border-radius: 8px !important; }
.logout-btn .stButton > button:hover { background: #2a1515 !important; }

[data-testid="stSidebar"] .stTextInput input { background: #1a1a1a !important; border: 1px solid #2a2a2a !important; color: #ececec !important; border-radius: 8px !important; font-size: 13px !important; }
[data-testid="stSidebar"] .stTextInput input:focus { box-shadow: none !important; border-color: #3f3f3f !important; }

.active-row .stButton > button { color: #fff !important; font-weight: 500; }
.user-profile-block { display: flex; align-items: center; gap: 11px; padding: 12px 14px; border-top: 1px solid #1e1e1e; background: #0f0f0f; cursor: pointer; transition: background .15s; }
.user-profile-block:hover { background: #161616; }
.avatar-circle { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #6366f1, #8b5cf6); display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; color: white; flex-shrink: 0; }
.uname  { font-size: 13.5px; font-weight: 600; color: #ececec; }
.uemail { font-size: 11px; color: #555; margin-top: 1px; }

.main .block-container { max-width: 800px; padding-top: 2rem; padding-bottom: 5rem; }
.wcard { background: #f8f8f8; border: 1px solid #e8e8e8; border-radius: 12px; padding: 18px; font-size: 13.5px; line-height: 1.6; color: #333; }
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

API_URL = "http://localhost:8004/chat"

# ── Helpers ───────────────────────────────────
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

# ── Session state defaults ────────────────────
for key, default in [
    ("logged_in",      False),
    ("auth_page",      "signin"),   # "signin" | "signup"
    ("user_name",      ""),
    ("user_email",     ""),
    ("user_id",        ""),
    ("all_chats",      {}),
    ("active_chat_id", None),
    ("ctx_open",       None),
    ("renaming_id",    None),
    ("user_menu_open", False),
    ("registered_users", {          # simple in-memory store; replace with DB
        "admin@erp.com": {"password": hash_pw("admin123"), "name": "Admin User", "id": "001"},
        "ck@erp.com":    {"password": hash_pw("ck123"),    "name": "CK",          "id": "002"},
    }),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def do_signup(name, email, password):
    db = st.session_state.registered_users
    email = email.lower().strip()
    if email in db:
        return False, "An account with this email already exists."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    new_id = str(len(db) + 1).zfill(3)
    db[email] = {"password": hash_pw(password), "name": name.strip(), "id": new_id}
    return True, "Account created! Please sign in."


def do_login(email, password):
    db  = st.session_state.registered_users
    email = email.lower().strip()
    user = db.get(email)
    if user and user["password"] == hash_pw(password):
        st.session_state.logged_in  = True
        st.session_state.user_email = email
        st.session_state.user_name  = user["name"]
        st.session_state.user_id    = user["id"]
        return True, ""
    return False, "Invalid email or password."


def do_logout():
    st.session_state.logged_in      = False
    st.session_state.user_name      = ""
    st.session_state.user_email     = ""
    st.session_state.user_id        = ""
    st.session_state.all_chats      = {}
    st.session_state.active_chat_id = None
    st.session_state.ctx_open       = None
    st.session_state.renaming_id    = None
    st.session_state.user_menu_open = False
    st.session_state.auth_page      = "signin"


def create_new_chat():
    chat_id = str(uuid.uuid4())
    st.session_state.all_chats[chat_id] = {"title": "New Chat", "messages": [], "created_at": datetime.now()}
    st.session_state.active_chat_id = chat_id
    st.session_state.ctx_open       = None
    st.session_state.renaming_id    = None
    return chat_id


def auto_title(chat_id, msg):
    st.session_state.all_chats[chat_id]["title"] = (msg[:40] + "...") if len(msg) > 40 else msg


# ══════════════════════════════════════════════
# AUTH PAGES
# ══════════════════════════════════════════════
if not st.session_state.logged_in:

    # ── Brand header ─────────────────────────
    st.markdown("""
    <div style="text-align:center; padding: 48px 0 28px;">
        <div style="
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 54px; height: 54px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            border-radius: 14px;
            font-size: 26px;
            margin-bottom: 14px;
            box-shadow: 0 4px 14px rgba(99,102,241,0.35);
        ">💬</div>
        <div style="
            font-size: 22px;
            font-weight: 700;
            color: #111;
            letter-spacing: -0.4px;
            line-height: 1.2;
            margin-bottom: 6px;
        ">QueryBridge AI</div>
        <div style="
            font-size: 13.5px;
            color: #aaa;
            font-weight: 400;
            letter-spacing: 0.1px;
        ">Your intelligent ERP assistant</div>
    </div>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.4, 1])

    with col:
        st.markdown('<div class="auth-wrap">', unsafe_allow_html=True)

        # ══ SIGN UP PAGE ══════════════════════
        if st.session_state.auth_page == "signup":
            st.markdown("### Create your account")
            st.markdown("<br>", unsafe_allow_html=True)

            full_name  = st.text_input("Full Name",  placeholder="John Smith",        key="su_name")
            email_su   = st.text_input("Email",      placeholder="you@example.com",   key="su_email")
            pass_su    = st.text_input("Password",   placeholder="Min 6 characters",  key="su_pass",  type="password")
            pass_su2   = st.text_input("Confirm Password", placeholder="Re-enter password", key="su_pass2", type="password")

            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
            if st.button("Create Account", key="signup_btn", use_container_width=True):
                if not full_name or not email_su or not pass_su or not pass_su2:
                    st.error("Please fill in all fields.")
                elif pass_su != pass_su2:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = do_signup(full_name, email_su, pass_su)
                    if ok:
                        st.success(msg)
                        st.session_state.auth_page = "signin"
                        st.rerun()
                    else:
                        st.error(msg)
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="or-divider">or</div>', unsafe_allow_html=True)
            st.markdown("Already have an account?")
            st.markdown('<div class="link-btn">', unsafe_allow_html=True)
            if st.button("Sign In instead", key="goto_signin"):
                st.session_state.auth_page = "signin"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        # ══ SIGN IN PAGE ══════════════════════
        elif st.session_state.auth_page == "forgot":
            st.markdown("### Reset your password")
            st.markdown('<p style="color:#999;font-size:13px;margin-bottom:20px;">Enter your email and we\'ll send a reset link.</p>', unsafe_allow_html=True)

            fp_email = st.text_input("Email", placeholder="you@example.com", key="fp_email")
            st.markdown("<br>", unsafe_allow_html=True)

            st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
            if st.button("Send Reset Link", key="reset_btn", use_container_width=True):
                if not fp_email:
                    st.error("Please enter your email address.")
                elif fp_email.lower().strip() not in st.session_state.registered_users:
                    st.error("No account found with that email.")
                else:
                    # ── Replace this with real email sending logic ──
                    st.success(f"Reset link sent to {fp_email} ✓")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="link-btn">', unsafe_allow_html=True)
            if st.button("← Back to Sign In", key="back_signin"):
                st.session_state.auth_page = "signin"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        else:
            st.markdown("### Welcome back")
            st.markdown("<br>", unsafe_allow_html=True)
            email = st.text_input("Email",    placeholder="you@example.com", key="si_email")
            pw    = st.text_input("Password", placeholder="••••••••",        key="si_pw", type="password")

            # Forgot password — right aligned
            _, fp_col = st.columns([3, 1])
            with fp_col:
                st.markdown('<div class="forgot-wrap">', unsafe_allow_html=True)
                if st.button("Forgot password?", key="forgot_pw"):
                    st.session_state.auth_page = "forgot"
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            # Login button
            st.markdown('<div class="login-btn">', unsafe_allow_html=True)
            if st.button("Login", key="signin_btn", use_container_width=True):
                if not email or not pw:
                    st.error("Please enter your email and password.")
                else:
                    ok, msg = do_login(email, pw)
                    if ok: st.rerun()
                    else:  st.error(msg)
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Don't have an account
            st.markdown('<p style="text-align:center;color:#888;font-size:13.5px;margin:0;">Don\'t have an account?</p>', unsafe_allow_html=True)
            _, su_col, _ = st.columns([2, 1, 2])
            with su_col:
                st.markdown('<div class="signup-inline">', unsafe_allow_html=True)
                if st.button("Sign up", key="go_signup"):
                    st.session_state.auth_page = "signup"
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    st.stop()


# ══════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════
with st.sidebar:
    st.markdown('<div style="padding:16px 14px 8px;font-size:15px;font-weight:700;color:#fff;">💬 QueryBridge AI</div>', unsafe_allow_html=True)

    if st.button("＋   New Chat", key="new_chat_btn", use_container_width=True):
        create_new_chat()
        st.rerun()

    st.markdown("---")
    st.session_state.user_id = st.text_input("User ID", value=st.session_state.user_id, key="uid_field")
    st.markdown("---")

    # ── Chat list ─────────────────────────────
    if st.session_state.all_chats:
        st.markdown('<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:#555;padding:4px 4px 6px 10px;">Recents</div>', unsafe_allow_html=True)

        for chat_id, chat_data in sorted(st.session_state.all_chats.items(), key=lambda x: x[1]["created_at"], reverse=True):
            is_active   = chat_id == st.session_state.active_chat_id
            is_renaming = st.session_state.renaming_id == chat_id
            ctx_open    = st.session_state.ctx_open == chat_id

            if is_renaming:
                new_title = st.text_input("New name", value=chat_data["title"], key=f"ri_{chat_id}", label_visibility="collapsed")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown('<div class="save-btn">', unsafe_allow_html=True)
                    if st.button("✓  Save", key=f"save_{chat_id}", use_container_width=True):
                        st.session_state.all_chats[chat_id]["title"] = new_title.strip() or "New Chat"
                        st.session_state.renaming_id = None
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                with c2:
                    st.markdown('<div class="cancel-btn">', unsafe_allow_html=True)
                    if st.button("✕  Cancel", key=f"canc_{chat_id}", use_container_width=True):
                        st.session_state.renaming_id = None
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                col_title, col_dot = st.columns([7, 1])
                with col_title:
                    st.markdown(f'<div class="{"active-row" if is_active else ""}">', unsafe_allow_html=True)
                    if st.button(("" if is_active else "") + chat_data["title"], key=f"sel_{chat_id}", use_container_width=True):
                        st.session_state.active_chat_id = chat_id
                        st.session_state.ctx_open = None
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                with col_dot:
                    st.markdown('<div class="menu-col">', unsafe_allow_html=True)
                    if st.button("⋯", key=f"dot_{chat_id}"):
                        st.session_state.ctx_open = chat_id if not ctx_open else None
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

                # Context menu
                if ctx_open:
                    cid = chat_id  # capture current chat_id for closure
                    st.markdown("""
                    <style>
                    .ctx-box-v2 {
                        background: #1f1f1f;
                        border: 1px solid #2e2e2e;
                        border-radius: 12px;
                        padding: 5px;
                        margin: 2px 6px 6px 6px;
                        box-shadow: 0 8px 28px rgba(0,0,0,0.6);
                    }
                    .ctx-box-v2 .stButton > button {
                        all: unset !important;
                        display: flex !important;
                        align-items: center !important;
                        gap: 10px !important;
                        width: 100% !important;
                        padding: 9px 13px !important;
                        border-radius: 8px !important;
                        font-size: 13.5px !important;
                        color: #d5d5d5 !important;
                        cursor: pointer !important;
                        transition: background 0.12s !important;
                        box-sizing: border-box !important;
                    }
                    .ctx-box-v2 .stButton > button:hover {
                        background: #2a2a2a !important;
                        color: #fff !important;
                    }
                    .ctx-del-v2 .stButton > button {
                        color: #f06060 !important;
                    }
                    .ctx-del-v2 .stButton > button:hover {
                        background: #2a1414 !important;
                        color: #ff7575 !important;
                    }
                    .ctx-divider {
                        height: 1px;
                        background: #2a2a2a;
                        margin: 3px 8px;
                    }
                                /* Forgot password link */
                                .forgot-wrap .stButton > button {
                                    all: unset !important;
                                    color: #6366f1 !important;
                                    font-size: 13px !important;
                                    cursor: pointer !important;
                                    float: right !important;
                                    padding: 0 !important;
                                    background: none !important;
                                    border: none !important;
                                    box-shadow: none !important;
                                }
                                .forgot-wrap .stButton > button:hover { text-decoration: underline !important; }

                                /* Login button */
                                .login-btn .stButton > button {
                                    all: unset !important;
                                    display: block !important;
                                    width: 100% !important;
                                    background: #111 !important;
                                    color: #fff !important;
                                    font-size: 15px !important;
                                    font-weight: 600 !important;
                                    padding: 13px 0 !important;
                                    border-radius: 10px !important;
                                    text-align: center !important;
                                    cursor: pointer !important;
                                    box-sizing: border-box !important;
                                    transition: background 0.2s !important;
                                }
                                .login-btn .stButton > button:hover { background: #333 !important; }

                                /* Sign up inline link */
                                .signup-inline .stButton > button {
                                    all: unset !important;
                                    color: #6366f1 !important;
                                    font-size: 13.5px !important;
                                    cursor: pointer !important;
                                    font-weight: 500 !important;
                                    padding: 0 !important;
                                    background: none !important;
                                    border: none !important;
                                    box-shadow: none !important;
                                    display: block !important;
                                    text-align: center !important;
                                }
                                .signup-inline .stButton > button:hover { text-decoration: underline !important; }
                    </style>
                    """, unsafe_allow_html=True)

                    st.markdown('<div class="ctx-box-v2">', unsafe_allow_html=True)

                    # Rename
                    if st.button("✏️   Rename", key=f"ren_{cid}", use_container_width=True):
                        st.session_state.renaming_id = cid
                        st.session_state.ctx_open = None; st.rerun()

                    st.markdown('<div class="ctx-divider"></div>', unsafe_allow_html=True)

                    # Delete
                    st.markdown('<div class="ctx-del-v2">', unsafe_allow_html=True)
                    if st.button("🗑️   Delete", key=f"del_{cid}", use_container_width=True):
                        del st.session_state.all_chats[cid]
                        if st.session_state.active_chat_id == cid:
                            st.session_state.active_chat_id = None
                        st.session_state.ctx_open = None; st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

                    st.markdown('</div>', unsafe_allow_html=True)  # /ctx-box-v2
    else:
        st.markdown('<div style="padding:8px 10px;font-size:13px;color:#444;">No chats yet.</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── User menu popup ───────────────────────
    if st.session_state.user_menu_open:
        st.markdown('<div class="user-menu-box">', unsafe_allow_html=True)
        st.markdown('<div class="logout-btn">', unsafe_allow_html=True)
        if st.button("   Log out", key="menu_logout", use_container_width=True):
            do_logout()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Profile bar ───────────────────────────
    initials = "".join(w[0].upper() for w in st.session_state.user_name.split()[:2]) or "U"
    col_profile, col_dots = st.columns([5, 1])
    with col_profile:
        st.markdown(f"""
        <div class="user-profile-block" style="border-top:none;padding:10px 4px;">
            <div class="avatar-circle">{initials}</div>
            <div style="flex:1;overflow:hidden;">
                <div class="uname">{st.session_state.user_name}</div>
                <div class="uemail">{st.session_state.user_email}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_dots:
        st.markdown('<div class="menu-col">', unsafe_allow_html=True)
        if st.button("⋯", key="profile_toggle"):
            st.session_state.user_menu_open = not st.session_state.user_menu_open
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:70px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# MAIN AREA
# ══════════════════════════════════════════════
if st.session_state.active_chat_id is None:
    st.markdown(f"## 👋 Welcome, {st.session_state.user_name}!")
    st.markdown("Your intelligent ERP data assistant.")
    st.markdown("---")
    for col, (title, desc) in zip(st.columns(3), [
        ("📊 Sales Analysis", "Revenue trends, average basket size, top customers, and sales performance."),
        ("📦 Inventory",      "Stock levels, low inventory alerts, product movement, and warehouse data."),
        ("💰 Financials",     "Outstanding balances, payment status, aging reports, and cash flow."),
    ]):
        with col:
            st.markdown(f'<div class="wcard"><b>{title}</b><br><br>{desc}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("✏️  Start New Chat"):
        create_new_chat()
        st.rerun()

else:
    active_chat = st.session_state.all_chats[st.session_state.active_chat_id]

    for msg in active_chat["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Message QueryBridge AI...")

    if user_input:
        chat_id  = st.session_state.active_chat_id
        messages = st.session_state.all_chats[chat_id]["messages"]

        if len(messages) == 0:
            auto_title(chat_id, user_input)

        messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    res = requests.post(API_URL, json={
                        "user_id":    st.session_state.user_id,
                        "session_id": chat_id,
                        "role":       "user",
                        "query":      user_input
                    }, timeout=30)
                    res.raise_for_status()
                    bot_reply = res.json().get("response", "No response from server.")
                except requests.exceptions.ConnectionError:
                    bot_reply = "❌ Cannot connect to backend. Is FastAPI running on port 8004?"
                except requests.exceptions.Timeout:
                    bot_reply = "⏱️ Request timed out."
                except requests.exceptions.HTTPError as e:
                    bot_reply = f"⚠️ Server error: {e.response.status_code}"
                except Exception as e:
                    bot_reply = f"❌ Unexpected error: {e}"
            st.markdown(bot_reply)

        messages.append({"role": "assistant", "content": bot_reply})
        st.rerun()