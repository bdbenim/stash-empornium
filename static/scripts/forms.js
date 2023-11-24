try {
  let enabled = document.getElementById("enable_form");
  function toggle() {
    const form = document.querySelector("#enable_form").parentElement.closest("form");
    for (el of form.querySelectorAll("input")) {
      if (el.id != "csrf_token" && el.id != "save" && el.id != enabled.id) {
        el.disabled = !enabled.checked;
      }
    }
  }
  enabled.onchange = toggle;
  toggle();
} catch {}

function showPass(id) {
  let el = document.getElementById(id);
  console.log("btn-" + el.id);
  let btn = document.getElementById("btn-" + el.id).querySelector("i");
  if (el.type === "password") {
    el.type = "text";
    btn.classList.remove("bi-eye-fill");
    btn.classList.add("bi-eye-slash-fill");
  } else {
    el.type = "password";
    btn.classList.remove("bi-eye-slash-fill");
    btn.classList.add("bi-eye-fill");
  }
}
