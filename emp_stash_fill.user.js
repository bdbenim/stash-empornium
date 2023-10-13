// ==UserScript==
// @name         Stash upload helper
// @namespace    http://tampermonkey.net/
// @version      0.1.2
// @description  This script helps create an upload for empornium based on a scene from your local stash instance.
// @author       You
// @match        https://www.empornium.sx/upload.php*
// @match        https://www.empornium.is/upload.php*
// @icon         data:image/x-icon;base64,AAABAAEAEBAAAAEAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAIAAAAAAAAAAAABMLAAATCwAAAAAAAAAAAABrPxj/az8Y/2s/GP9rPxj/cUMV/3tKFf+DUBP/gk8S/4BOEf9/TA//dkcR/29CE/9rPxj/az8Y/2s/GP9rPxj/az8Y/2s/GP9rPxf/gU8U/5FbF/+OWRf/jFcX/3FGEv9FKwv/RCoK/0MpCf9iPAz/eEcQ/2s/F/9rPxj/az8Y/2s/GP9rPxf/iFUU/5dgFv+UXhb/iVYW/zYoF/+BgYH/wMDA///////AwMD/gYGB/yshFP96ShD/az8X/2s/GP9rPxj/hlMU/5xkFv+aYxb/j1sV/y4kFv/Q0ND//////+Dg3//Q0ND///////////+RkZD/ZD0O/3hIEf9rPxj/dEUV/6JpF/+gZxb/nmYW/08zDP/AwMD///////////80LiT/HhQG////////////wMDA/2Y/EP+GUhP/cEIU/4dUFf+mbBj/pGoX/6FoFv9GPzT////////////g4N//QysL/0tIQ////////////5GRkP9pQRH/iVQV/3lJE/+dZRj/qm8b/6dtGf+HWBT/cXFx////////////kZGQ/0UtC/9iYmH/wMDA/8DAwP9SUlH/hlQW/4xXF/+EURT/oGga/65yHf+rcBz/YEAQ/8DAwP///////////1JSUf8WDwT/AwMC/wMDAv8fFAb/SzAM/5JcF/+QWhf/hlMU/6NqHP+ydiH/sHQf/0g1Gv//////////////////////////////////////4ODf/00yDP+WXxb/k10X/4lVFP+mbR//tnkk/7N3Iv9SUlH///////////+hoaD/oaGg/////////////////6GhoP9iPw7/mWIW/5dgFv+MVxP/j1sc/7p9J/+LXR3/gYGB////////////KCEV/1JSUf////////////////9SUlH/lWAV/51lFv+bYxb/gE8U/3dIF/++gCv/jl8f/8DAwP///////////xkRBv+hoaD////////////AwMD/QCoK/6NpF/+gaBb/nmYW/3NFFf9rPxj/l2Ef/5xqJP+BgYH///////////+hoaD////////////Q0ND/KCAV/55oGf+mbBj/pGoX/4dVFP9rPxj/az8Y/2s/F/+iayP/PysQ/4GBgf/Q0ND/7+/v/8DAwP9xcXH/PzAa/6VtHf+tcR3/qm8b/5JcFv9rPxf/az8Y/2s/GP9rPxj/az8X/5ljIP+HXCH/YkMY/2FCFv9fQRb/l2Ug/7Z5JP+zdyL/sXUg/41ZF/9rPxf/az8Y/2s/GP9rPxj/az8Y/2s/GP9rPxj/d0gY/5NeH/+tciT/q3Ej/6lvIf+nbiD/jVka/3ZHFv9rPxj/az8Y/2s/GP9rPxj/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP//AAD//w==
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @homepageURL  https://github.com/bdbenim/stash-empornium
// @updateURL    https://github.com/bdbenim/stash-empornium/raw/main/emp_stash_fill.user.js
// @downloadURL  https://github.com/bdbenim/stash-empornium/raw/main/emp_stash_fill.user.js
// ==/UserScript==

// Changelog:
// v0.1.2
//  - Add Open Stash button
// v0.1.1
//  - Fixed default values in settings menu
// v0.1.0
//  - Display filename in place of title if title is null

const BACKEND_DEFAULT = "http://localhost:9932"
const STASH_DEFAULT = "http://localhost:9999"
const STASH_API_KEY_DEFAULT = null;

var BACKEND = GM_getValue("backend_url", BACKEND_DEFAULT);
var STASH = GM_getValue("stash_url", STASH_DEFAULT);
var STASH_API_KEY = GM_getValue("stash_api_key", STASH_API_KEY_DEFAULT);

function store(key, prompt_text, default_value) {
    let oldvalue = GM_getValue(key, default_value);
    GM_setValue(key, prompt(prompt_text, oldvalue) || oldvalue);
}

GM_registerMenuCommand("Set backend URL", () => {store("backend_url","backend url? (e.g. http://localhost:9932)",BACKEND_DEFAULT);});
GM_registerMenuCommand("Set stash URL", () => {store("stash_url","stash URL? (e.g. http://localhost:9999)",STASH_DEFAULT);});
GM_registerMenuCommand("Set stash API key", () => {store("stash_api_key","stash API key?",STASH_API_KEY_DEFAULT);});

GM_addStyle("#stash_statusarea { font-weight: bold; font-size: 16pt; padding-top: 12pt; text-align: center; }");
GM_addStyle("#stash_statusarea:empty { padding: 0; }");
GM_addStyle("#stash_instructions { font-size: 12pt; padding: 12pt 0; margin-left: auto; margin-right: auto; max-width: 600px; }");
GM_addStyle("#stash_instructions:empty { padding: 0; }");
GM_addStyle("#stash_instructions li + li { padding-top: 12pt; }");
GM_addStyle("#stash_instructions > ol { padding-top: 12pt; }");
GM_addStyle("#stash_instructions input { width: 100%; font-family: monospace; font-size: 10pt; }");

var graphql = {
    method: "POST",
    headers: {
        "Content-Type": "application/json"
    },
    url: new URL("/graphql", STASH).href,
};

if (STASH_API_KEY !== null) {
    graphql.headers.apiKey = STASH_API_KEY;
}

(function() {
    'use strict';

    let parent = document.getElementsByClassName("thin")[0];

    let head = document.createElement("div");
    head.classList.add("head");
    head.innerHTML = "Fill from Stash";

    let body = document.createElement("div");
    body.classList.add("box", "pad");

    let fileSelect = document.createElement("select");
    fileSelect.style.marginLeft = "12pt";
    fileSelect.style.width = "auto";

    let titleDisplay = document.createElement("input");
    titleDisplay.setAttribute("disabled", true);
    titleDisplay.style.marginLeft = "12pt";
    titleDisplay.setAttribute("size", 60);

    let templateSelect = document.createElement("select");
    templateSelect.style.marginLeft = "12pt";
    GM_xmlhttpRequest({
        method: "GET",
        url: new URL("/templates", BACKEND).href,
        context: { templateSelect: templateSelect },
        responseType: "json",
        onload: function(response) {
            let optionsAsString = "";
            for(let key in response.response) {
                optionsAsString += "<option value='" + key + "'>" + response.response[key] + "</option>";
            }
            this.context.templateSelect.innerHTML = optionsAsString;
        }
    });

    let fillButton = document.createElement("input");
    fillButton.setAttribute("type", "submit");
    fillButton.setAttribute("value", "fill from");
    fillButton.style.marginLeft = "12pt";

    let stashButton = document.createElement("input");
    stashButton.setAttribute("type", "submit");
    stashButton.setAttribute("value", "Open Stash");
    stashButton.style.marginLeft = "12pt";

    let moreOptions = document.createElement("div");
    moreOptions.style.marginTop = "12pt";
    let screensToggleLabel = document.createElement("label");
    screensToggleLabel.setAttribute("for", "screenstoggle");
    screensToggleLabel.innerText = "Generate screens? (contact sheet is always generated)";
    screensToggleLabel.style.marginRight = "6pt";
    let screensToggle = document.createElement("input");
    screensToggle.setAttribute("type", "checkbox");
    screensToggle.setAttribute("name", "screenstoggle");
    screensToggle.setAttribute("id", "screenstoggle");
    screensToggle.setAttribute("checked", true);
    moreOptions.appendChild(screensToggleLabel);
    moreOptions.appendChild(screensToggle);
    moreOptions.appendChild(templateSelect);

    let statusArea = document.createElement("div");
    statusArea.setAttribute("id", "stash_statusarea");

    let instructions = document.createElement("div");
    instructions.setAttribute("id", "stash_instructions");

    let idInput = document.createElement("input");
    idInput.setAttribute("size", 8);
    idInput.setAttribute("type", "text");
    idInput.setAttribute("id", "stash_id");
    idInput.setAttribute("placeholder", "Stash ID");

    const announceURL = document.evaluate("//input[contains(@value,'/announce')]", document, null, XPathResult.ANY_UNORDERED_NODE_TYPE, null).singleNodeValue.value;

    fillButton.addEventListener("click", () => {
        statusArea.innerHTML = "";
        instructions.innerHTML = "";
        GM_xmlhttpRequest({
            method: "POST",
            headers: { "Content-Type": "application/json" },
            url: new URL("/fill", BACKEND).href,
            responseType: "stream",
            data: JSON.stringify({ scene_id: idInput.value, file_id: fileSelect.value, announce_url: announceURL, template: templateSelect.value, screens: screensToggle.checked }),
            context: {
                statusArea: statusArea,
                description: document.getElementById("desc"),
                tags: document.getElementById("taginput"),
                cover: document.getElementById("image"),
                title: document.getElementById("title"),
                instructions: instructions
            },
            onreadystatechange: async function(response) {
                if (response.readyState == 2 && response.status == 200) {
                    const reader = response.response.getReader();
                    while (true) {
                        const { done, value } = await reader.read(); // value is Uint8Array
                        if (value) {
                            let text = new TextDecoder().decode(value);
                            let j;
                            try {
                               j = JSON.parse(text);
                            } catch (e) {
                               if (text.includes('"message": "Done"')) {
                                  console.debug("The response stream was incomplete, reading until end of stream.");
                                  const stashData = [];
                                  stashData.push(text);
                                  while (true) {
                                     let { done, value } = await reader.read();
                                     stashData.push(new TextDecoder().decode(value));
                                     if (done) break;
                                  }
                                  text = stashData.join("");
                                  console.debug(text);
                                  j = JSON.parse(text);
                               } else {
                                  console.warn("Unexpected failure to read stream data.");
                               }
                            }
                            if (j.status === "success") {
                                if ("message" in j.data) {
                                    this.context.statusArea.innerText = j.data.message;
                                }
                                if ("fill" in j.data) {
                                    this.context.description.value = j.data.fill.description;
                                    this.context.tags.value = j.data.fill.tags;
                                    this.context.cover.value = j.data.fill.cover;
                                    this.context.title.value = j.data.fill.title;
                                    let instructions = "";
                                    instructions += "Instructions:<ol>";
                                    instructions += '<li>Set a category for the upload and double-check everything for correctness</li>';
                                    instructions += '<li>Make sure the generated torrent is in your torrent client, and attach it to the upload form manually as usual:<div><input type="text" value="' + j.data.fill.torrent_path + '" disabled></div></li>';
                                    instructions += '<li>Make sure the media file is in the torrents path of your torrent client:<div><input type="text" value="' + j.data.fill.file_path + '" disabled></div></li>';
                                    instructions += "</ol>";
                                    this.context.instructions.innerHTML = instructions;
                                }
                            }
                            else if (j.status === "error") {
                                this.context.statusArea.innerHTML = "<span style='color: red;'>" + j.message + "</span>";
                                break;
                            }
                        }
                        if (done) break;
                    }
                }
            }
        });
    });

    stashButton.addEventListener("click", function() {
        let idInput = document.getElementById("stash_id");
        if (idInput.value.length > 0) {
            window.open(STASH + "/scenes/" + idInput.value, '_blank');
        }
        else {
            window.open(STASH, '_blank');
        }
    });

    idInput.addEventListener("input", function(event) {
        GM_xmlhttpRequest(Object.assign({}, graphql, {
            data: JSON.stringify({
                "query": '{ findScene(id: "' + idInput.value + '") { id title performers { id name image_path } files { id basename path format width height video_codec audio_codec duration bit_rate frame_rate } } }',
            }),
            context: { fileSelect: fileSelect, titleDisplay: titleDisplay },
            onload: function(response) {
                try {
                    let scene = JSON.parse(response.responseText).data.findScene;
                    let optionsAsString = "";
                    if (scene.title.length > 0) {
                        this.context.titleDisplay.value = scene.title;
                    }
                    else {
                        this.context.titleDisplay.value = scene.files[0].basename;
                    }
                    for(let i = 0; i < scene.files.length; i++) {
                        let file = scene.files[i];
                        let duration = new Date(file.duration * 1000).toISOString().slice(11, 19).replace(/^00:/, '');
                        optionsAsString += "<option value='" + file.id + "'>" + file.width + "×" + file.height + ", " + file.format + ", " + file.video_codec + "/" + file.audio_codec + ", " + duration + "</option>";
                    }
                    this.context.fileSelect.innerHTML = optionsAsString;
                }
                catch(err) {
                    this.context.titleDisplay.value = "";
                    this.context.fileSelect.innerHTML = "";
                }
            },
        }));
        if (event.target.value === "") {
            titleDisplay.value = "";
            fileSelect.innerHTML = "";
        }
        statusArea.innerHTML = "";
        instructions.innerHTML = "";
    } );

    body.appendChild(idInput);
    body.appendChild(titleDisplay);
    body.appendChild(fileSelect);
    body.appendChild(fillButton);
    body.appendChild(stashButton);
    body.appendChild(moreOptions);
    body.appendChild(statusArea);
    body.appendChild(instructions);

    parent.insertBefore(body, parent.children[5]);
    parent.insertBefore(head, body);

})();
