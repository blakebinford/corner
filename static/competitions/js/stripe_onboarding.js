let connectedAccountId = null;
const signUpBtn = document.getElementById("sign-up-button");
const addInfoBtn = document.getElementById("add-information-button");

signUpBtn.onclick = async () => {
  document.getElementById("dev-callout").classList.remove("hidden");
  document.getElementById("creating-connected-account").classList.remove("hidden");
  signUpBtn.classList.add("hidden");
  document.getElementById("error").classList.add("hidden");

  const res = await fetch("/stripe/account/", { method: "POST" });
  const { account, error } = await res.json();
  if (error) return showError();

  connectedAccountId = account;
  document.getElementById("connected-account-id")
          .innerHTML = `Your account ID: <code>${connectedAccountId}</code>`;
  document.getElementById("connected-account-id").classList.remove("hidden");
  addInfoBtn.classList.remove("hidden");
  document.getElementById("creating-connected-account").classList.add("hidden");
  document.getElementById("title").classList.add("hidden");
  document.getElementById("subtitle").classList.add("hidden");
};

addInfoBtn.onclick = () => createLinkAndRedirect();

async function createLinkAndRedirect() {
  document.getElementById("adding-onboarding-information").classList.remove("hidden");
  addInfoBtn.classList.add("hidden");
  const res = await fetch("/stripe/account_link/", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ account: connectedAccountId })
  });
  const { url, error } = await res.json();
  if (error) return showError();
  window.location.href = url;
}

function showError() {
  document.getElementById("error").classList.remove("hidden");
  signUpBtn.classList.remove("hidden");
  addInfoBtn.classList.remove("hidden");
}
