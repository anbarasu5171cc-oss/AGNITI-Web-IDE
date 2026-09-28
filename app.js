const DEFAULT_PROGRAM =
`START

Step 1: Display "Hello, world!"

END`;

const editor = document.getElementById("editor");
const lineNumbers = document.getElementById("line-numbers");
const output = document.getElementById("output");
const runtimeStatus = document.getElementById("runtime-status");
const runButton = document.getElementById("run-btn");
const runTime = document.getElementById("run-time");
const outputFooter = document.getElementById("output-footer");

let backendReady = false;
let deferredInstallPrompt = null;


// =====================================================
// STATUS
// =====================================================

function setStatus(message, state = "") {
    runtimeStatus.className =
        `status-pill ${state}`.trim();

    const textNode = runtimeStatus.lastChild;

    if (textNode) {
        textNode.textContent = ` ${message}`;
    }
}


// =====================================================
// LINE NUMBERS
// =====================================================

function updateLineNumbers() {
    const lines =
        editor.value.split("\n").length;

    lineNumbers.textContent =
        Array.from(
            { length: lines },
            (_, i) => i + 1
        ).join("\n");

    document.getElementById(
        "line-count"
    ).textContent =
        `${lines} line${lines === 1 ? "" : "s"}`;

    const position =
        editor.selectionStart;

    const before =
        editor.value
            .slice(0, position)
            .split("\n");

    document.getElementById(
        "cursor-info"
    ).textContent =
        `Ln ${before.length}, Col ${
            before[before.length - 1].length + 1
        }`;

    lineNumbers.scrollTop =
        editor.scrollTop;
}


// =====================================================
// STEP NUMBERING
// =====================================================

function renumberSteps(source) {
    let count = 0;

    return source
        .split("\n")
        .map(line => {

            if (
                /^\s*Step\s+\d+\s*:/i.test(line)
            ) {
                count++;

                return line.replace(
                    /^\s*Step\s+\d+\s*:/i,
                    `Step ${count}:`
                );
            }

            return line;
        })
        .join("\n");
}


function setEditorValue(
    source,
    renumber = true
) {
    editor.value =
        renumber
            ? renumberSteps(source)
            : source;

    updateLineNumbers();
}


// =====================================================
// OUTPUT
// =====================================================

function setOutput(
    text,
    error = false,
    footer = "Finished"
) {
    output.textContent =
        text ||
        (
            error
                ? "Program failed without producing an error message."
                : "Program finished with no output."
        );

    output.classList.toggle(
        "error",
        error
    );

    outputFooter.classList.toggle(
        "failed",
        error
    );

    const footerText =
        outputFooter.lastChild;

    if (footerText) {
        footerText.textContent =
            ` ${footer}`;
    }
}


// =====================================================
// FILE DOWNLOAD
// =====================================================

function downloadText(
    filename,
    content,
    mime = "text/plain;charset=utf-8"
) {
    const blob =
        new Blob(
            [content],
            { type: mime }
        );

    const url =
        URL.createObjectURL(blob);

    const link =
        document.createElement("a");

    link.href = url;
    link.download = filename;

    document.body.appendChild(link);
    link.click();
    link.remove();

    setTimeout(
        () => URL.revokeObjectURL(url),
        1000
    );
}


function getFilename() {
    let name =
        document
            .getElementById("filename")
            .value
            .trim() ||
        "untitled.agn";

    if (
        !name
            .toLowerCase()
            .endsWith(".agn")
    ) {
        name += ".agn";
    }

    return name.replace(
        /[\\/:*?"<>|]/g,
        "_"
    );
}


// =====================================================
// BACKEND CONNECTION
// =====================================================

async function checkBackend() {
    try {

        const response =
            await fetch(
                "/api/health",
                {
                    method: "GET",
                    cache: "no-store"
                }
            );

        if (!response.ok) {
            throw new Error(
                "Backend unavailable"
            );
        }

        const data =
            await response.json();

        if (
            !data ||
            data.status !== "ok"
        ) {
            throw new Error(
                "Invalid backend response"
            );
        }

        backendReady = true;

        runButton.disabled = false;

        setStatus(
            "Backend ready",
            "ready"
        );

        setOutput(
            "Welcome to AGNITI Web IDE.\n\nPress “Run program” to execute your code.",
            false,
            "Ready"
        );

    } catch (error) {

        backendReady = false;

        runButton.disabled = true;

        setStatus(
            "Backend unavailable",
            "error"
        );

        setOutput(
            "Cannot connect to the AGNITI Python backend.\n\nStart server.py and reload this page.",
            true,
            "Backend unavailable"
        );
    }
}


// =====================================================
// EDITOR EVENTS
// =====================================================

editor.addEventListener(
    "input",
    updateLineNumbers
);

editor.addEventListener(
    "click",
    updateLineNumbers
);

editor.addEventListener(
    "keyup",
    updateLineNumbers
);

editor.addEventListener(
    "scroll",
    () => {
        lineNumbers.scrollTop =
            editor.scrollTop;
    }
);


// =====================================================
// TAB + AUTOMATIC STEP
// =====================================================

editor.addEventListener(
    "keydown",
    event => {

        if (event.key === "Tab") {

            event.preventDefault();

            const start =
                editor.selectionStart;

            const end =
                editor.selectionEnd;

            editor.setRangeText(
                "    ",
                start,
                end,
                "end"
            );

            updateLineNumbers();

            return;
        }


        if (
            event.key !== "Enter" ||
            event.shiftKey ||
            event.ctrlKey ||
            event.altKey ||
            event.metaKey
        ) {
            return;
        }


        const start =
            editor.selectionStart;

        const lineStart =
            editor.value.lastIndexOf(
                "\n",
                start - 1
            ) + 1;

        const lineEnd =
            editor.value.indexOf(
                "\n",
                start
            );

        const currentLine =
            editor.value.slice(
                lineStart,
                lineEnd === -1
                    ? editor.value.length
                    : lineEnd
            );


        if (
            !/^\s*Step\s+\d+\s*:/i.test(
                currentLine
            )
        ) {
            return;
        }


        event.preventDefault();


        const stepCount =
            (
                editor.value.match(
                    /^\s*Step\s+\d+\s*:/gim
                ) || []
            ).length;


        editor.setRangeText(
            `\nStep ${stepCount + 1}: `,
            start,
            editor.selectionEnd,
            "end"
        );

        updateLineNumbers();
    }
);


// =====================================================
// RUN AGNITI
// =====================================================

runButton.addEventListener(
    "click",
    async () => {

        if (!backendReady) {
            setOutput(
                "AGNITI backend is not available.",
                true,
                "Backend unavailable"
            );
            return;
        }


        const source =
            editor.value.trim();


        if (!source) {

            setOutput(
                "Write an AGNITI program before running.",
                true,
                "No source"
            );

            return;
        }


        runButton.disabled = true;


        setStatus(
            "Running...",
            "running"
        );


        setOutput(
            "Running AGNITI program...",
            false,
            "Running"
        );


        runTime.textContent = "—";


        const started =
            performance.now();


        try {

            const response =
                await fetch(
                    "/api/run",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body: JSON.stringify({
                            source: source
                        })
                    }
                );


            const data =
                await response.json();


            const clientElapsed =
                performance.now() - started;


            if (
                !response.ok ||
                !data.success
            ) {

                const message =
                    data.error ||
                    data.output ||
                    "AGNITI program failed.";

                setOutput(
                    message,
                    true,
                    "Failed"
                );

                runTime.textContent =
                    `${clientElapsed.toFixed(2)} ms`;

                setStatus(
                    "Execution failed",
                    "error"
                );

                return;
            }


            // Only backend output is shown.
            // Generated Python is NEVER displayed.

            setOutput(
                data.output || "",
                false,
                "Finished"
            );


            const backendTime =
                typeof data.runtime_ms === "number"
                    ? data.runtime_ms
                    : clientElapsed;


            runTime.textContent =
                `${backendTime.toFixed(2)} ms`;


            setStatus(
                "Program finished",
                "ready"
            );

        } catch (error) {

            setOutput(
                `Backend connection error: ${error.message}`,
                true,
                "Connection error"
            );

            setStatus(
                "Backend unavailable",
                "error"
            );

        } finally {

            runButton.disabled =
                !backendReady;
        }
    }
);


// =====================================================
// CLEAR OUTPUT
// =====================================================

document
    .getElementById("clear-btn")
    ?.addEventListener(
        "click",
        () => {

            setOutput(
                "Output cleared.",
                false,
                "Ready"
            );

            runTime.textContent =
                "—";

            setStatus(
                "Backend ready",
                "ready"
            );
        }
    );


// =====================================================
// NEW
// =====================================================

document
    .getElementById("new-btn")
    ?.addEventListener(
        "click",
        () => {

            setEditorValue(
                DEFAULT_PROGRAM,
                false
            );

            document
                .getElementById("filename")
                .value =
                "untitled.agn";


            setOutput(
                "New AGNITI file created.",
                false,
                "Ready"
            );

            runTime.textContent =
                "—";
        }
    );


// =====================================================
// SAVE
// =====================================================

document
    .getElementById("save-btn")
    ?.addEventListener(
        "click",
        () => {

            downloadText(
                getFilename(),
                editor.value,
                "text/plain;charset=utf-8"
            );

            setStatus(
                "File saved",
                "ready"
            );
        }
    );


// =====================================================
// OPEN
// =====================================================

document
    .getElementById("open-btn")
    ?.addEventListener(
        "click",
        () => {

            document
                .getElementById("file-picker")
                .click();
        }
    );


document
    .getElementById("file-picker")
    ?.addEventListener(
        "change",
        async event => {

            const file =
                event.target.files?.[0];

            if (!file) {
                return;
            }


            try {

                const text =
                    await file.text();


                setEditorValue(
                    text,
                    true
                );


                document
                    .getElementById("filename")
                    .value =
                    file.name;


                setOutput(
                    "File opened successfully.",
                    false,
                    "Ready"
                );

            } catch (error) {

                setOutput(
                    `Unable to open file: ${error.message}`,
                    true,
                    "Open failed"
                );
            }


            event.target.value =
                "";
        }
    );


// =====================================================
// EXAMPLE
// =====================================================

document
    .getElementById("example-btn")
    ?.addEventListener(
        "click",
        () => {

            setEditorValue(
                DEFAULT_PROGRAM,
                false
            );

            setOutput(
                "Example loaded.",
                false,
                "Ready"
            );

            runTime.textContent =
                "—";
        }
    );


// =====================================================
// PWA INSTALL
// =====================================================

window.addEventListener(
    "beforeinstallprompt",
    event => {

        event.preventDefault();

        deferredInstallPrompt =
            event;


        const installButton =
            document.getElementById(
                "install-btn"
            );


        if (installButton) {

            installButton.classList.remove(
                "hidden"
            );
        }
    }
);


document
    .getElementById("install-btn")
    ?.addEventListener(
        "click",
        async () => {

            if (!deferredInstallPrompt) {
                return;
            }


            deferredInstallPrompt.prompt();


            await deferredInstallPrompt.userChoice;


            deferredInstallPrompt =
                null;


            document
                .getElementById("install-btn")
                ?.classList.add(
                    "hidden"
                );
        }
    );


// =====================================================
// INITIALIZE
// =====================================================

setEditorValue(
    DEFAULT_PROGRAM,
    false
);

checkBackend();