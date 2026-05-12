/* Supabase auth + paywall handling for Berlin Property Finder. */

let supabaseClient = null;
let currentSession = null;
let appConfig = null;

async function initAuth() {
    try {
        const cfg = await fetch("/api/config").then(r => r.json());
        appConfig = cfg;
        if (!cfg.supabase_url || !cfg.supabase_anon_key) {
            console.warn("Supabase not configured");
            renderAuthHeader(null);
            return;
        }
        // supabase-js v2 is loaded via <script> in the template
        supabaseClient = supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);
        const { data: { session } } = await supabaseClient.auth.getSession();
        currentSession = session;
        renderAuthHeader(session);
        supabaseClient.auth.onAuthStateChange((_event, session) => {
            currentSession = session;
            renderAuthHeader(session);
        });
    } catch (err) {
        console.error("auth init failed", err);
    }
}

async function authHeader() {
    // Always ask Supabase for the freshest session — handles token refresh
    // and the early-load race where currentSession isn't populated yet.
    let token = currentSession && currentSession.access_token;
    if (!token && supabaseClient) {
        try {
            const { data } = await supabaseClient.auth.getSession();
            if (data && data.session) {
                currentSession = data.session;
                token = data.session.access_token;
            }
        } catch (e) {
            console.warn("getSession failed", e);
        }
    }
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

function renderAuthHeader(session) {
    const slot = document.getElementById("authSlot");
    if (!slot) return;
    slot.innerHTML = "";
    if (session && session.user) {
        const email = session.user.email || "Account";
        const wrap = document.createElement("div");
        wrap.className = "auth-wrap";
        wrap.innerHTML = `
            <span class="auth-email">${escapeHtml(email)}</span>
            <button class="auth-link" id="manageBtn">Manage</button>
            <button class="auth-link" id="logoutBtn">Sign out</button>
        `;
        slot.appendChild(wrap);
        document.getElementById("manageBtn").addEventListener("click", openPortal);
        document.getElementById("logoutBtn").addEventListener("click", async () => {
            await supabaseClient.auth.signOut();
        });
    } else {
        const btn = document.createElement("button");
        btn.className = "auth-link primary";
        btn.textContent = "Sign in";
        btn.addEventListener("click", () => openAuthModal("signin"));
        slot.appendChild(btn);
    }
}

function openAuthModal(_mode) {
    const m = document.getElementById("authModal");
    document.getElementById("authModalTitle").textContent = "Sign in";
    document.getElementById("authModalError").textContent = "";
    m.style.display = "flex";
}

function closeAuthModal() {
    document.getElementById("authModal").style.display = "none";
}

function openPaywall(reason) {
    const m = document.getElementById("paywallModal");
    const title = document.getElementById("paywallTitle");
    const sub = document.getElementById("paywallSubtitle");
    if (reason === "signup_required") {
        title.textContent = "Create a free account to continue";
        sub.textContent = "You've used your 2 free searches. Sign up to keep going — your account starts with 1 free search per day.";
        document.getElementById("paywallSignUp").style.display = "";
        document.getElementById("paywallPlans").style.display = "none";
    } else {
        title.textContent = "Subscribe to search";
        sub.textContent = "An active subscription is required to use the property search. Pick a plan to get unlimited access.";
        document.getElementById("paywallSignUp").style.display = "none";
        document.getElementById("paywallPlans").style.display = "";
    }
    m.style.display = "flex";
}

function closePaywall() {
    document.getElementById("paywallModal").style.display = "none";
}

async function startCheckout(plan) {
    if (!currentSession) {
        openAuthModal("signin");
        return;
    }
    const r = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(await authHeader()) },
        body: JSON.stringify({ plan, email: currentSession.user.email }),
    });
    const data = await r.json();
    if (data.url) {
        window.location.href = data.url;
    } else {
        alert("Checkout failed: " + (data.error || "unknown"));
    }
}

async function openPortal() {
    const r = await fetch("/api/portal", {
        method: "POST",
        headers: { ...(await authHeader()) },
    });
    const data = await r.json();
    if (data.url) {
        window.location.href = data.url;
    } else if (data.error === "no_customer") {
        // No subscription yet — show paywall
        openPaywall("subscribe_required");
    } else {
        alert("Portal failed: " + (data.error || "unknown"));
    }
}

async function signInWithOAuth(provider) {
    if (!supabaseClient) {
        document.getElementById("authModalError").textContent = "Auth not configured.";
        return;
    }
    const { error } = await supabaseClient.auth.signInWithOAuth({
        provider,
        options: { redirectTo: window.location.origin },
    });
    if (error) {
        document.getElementById("authModalError").textContent = error.message || "OAuth failed.";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initAuth();
    const closeBtn = document.getElementById("authModalClose");
    if (closeBtn) closeBtn.addEventListener("click", closeAuthModal);
    const googleBtn = document.getElementById("oauthGoogle");
    if (googleBtn) googleBtn.addEventListener("click", () => signInWithOAuth("google"));
    const appleBtn = document.getElementById("oauthApple");
    if (appleBtn) appleBtn.addEventListener("click", () => signInWithOAuth("apple"));
    const paywallClose = document.getElementById("paywallClose");
    if (paywallClose) paywallClose.addEventListener("click", closePaywall);
    document.querySelectorAll(".paywall-plan-btn").forEach(btn => {
        btn.addEventListener("click", () => startCheckout(btn.dataset.plan));
    });
    const paywallSignUpBtn = document.getElementById("paywallSignUp");
    if (paywallSignUpBtn) paywallSignUpBtn.addEventListener("click", () => {
        closePaywall();
        openAuthModal();
    });
    // Close on backdrop click
    ["authModal", "paywallModal"].forEach(id => {
        const m = document.getElementById(id);
        if (!m) return;
        m.addEventListener("click", e => {
            if (e.target === m) m.style.display = "none";
        });
    });
});
