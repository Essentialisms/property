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

function authHeader() {
    if (currentSession && currentSession.access_token) {
        return { "Authorization": `Bearer ${currentSession.access_token}` };
    }
    return {};
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

function openAuthModal(mode) {
    const m = document.getElementById("authModal");
    document.getElementById("authModalTitle").textContent =
        mode === "signup" ? "Create your account" : "Sign in";
    document.getElementById("authModalSwitch").innerHTML =
        mode === "signup"
            ? `Already have an account? <a href="#" id="switchToSignIn">Sign in</a>`
            : `New here? <a href="#" id="switchToSignUp">Create an account</a>`;
    document.getElementById("authModalSubmit").textContent =
        mode === "signup" ? "Sign up" : "Sign in";
    document.getElementById("authModalSubmit").dataset.mode = mode;
    document.getElementById("authModalError").textContent = "";
    m.style.display = "flex";
    document.getElementById("authEmail").focus();
    const switchSignIn = document.getElementById("switchToSignIn");
    const switchSignUp = document.getElementById("switchToSignUp");
    if (switchSignIn) switchSignIn.addEventListener("click", e => { e.preventDefault(); openAuthModal("signin"); });
    if (switchSignUp) switchSignUp.addEventListener("click", e => { e.preventDefault(); openAuthModal("signup"); });
}

function closeAuthModal() {
    document.getElementById("authModal").style.display = "none";
}

async function submitAuth() {
    const mode = document.getElementById("authModalSubmit").dataset.mode || "signin";
    const email = document.getElementById("authEmail").value.trim();
    const password = document.getElementById("authPassword").value;
    const errEl = document.getElementById("authModalError");
    errEl.textContent = "";
    if (!email || !password) {
        errEl.textContent = "Email and password required.";
        return;
    }
    if (!supabaseClient) {
        errEl.textContent = "Auth not configured.";
        return;
    }
    const fn = mode === "signup" ? supabaseClient.auth.signUp : supabaseClient.auth.signInWithPassword;
    const { data, error } = await fn.call(supabaseClient.auth, { email, password });
    if (error) {
        errEl.textContent = error.message || "Authentication failed.";
        return;
    }
    if (mode === "signup" && data && !data.session) {
        errEl.textContent = "Account created. Check your email to confirm, then sign in.";
        return;
    }
    closeAuthModal();
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
        title.textContent = "Upgrade to keep searching";
        sub.textContent = "You've used today's free search. Pick a plan for unlimited.";
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
        headers: { "Content-Type": "application/json", ...authHeader() },
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
        headers: { ...authHeader() },
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
    const submitBtn = document.getElementById("authModalSubmit");
    if (submitBtn) submitBtn.addEventListener("click", submitAuth);
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
        openAuthModal("signup");
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
