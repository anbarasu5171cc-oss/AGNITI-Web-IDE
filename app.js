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
// PYTHON-IN-THE-BROWSER RUNTIME
// =====================================================

let pyodide = null;
let runtimeReady = false;
let runtimeLoading = false;

const COMPILER_FILES = [
    "compiler/lexer.py",
    "compiler/parser.py",
    "compiler/code_generator.py"
];


function appendRuntimeOutput(chunk) {
    runtimeOutput += String(chunk);
}


async function loadCompilerFiles() {
    for (const file of COMPILER_FILES) {
        const response = await fetch(file, { cache: "no-store" });

        if (!response.ok) {
            throw new Error(`Unable to load ${file} (${response.status})`);
        }

        const source = await response.text();
        const target = `/home/pyodide/${file.split("/").pop()}`;

        pyodide.FS.writeFile(target, source);
    }
}


async function initializePythonRuntime() {
    if (runtimeReady) {
        return;
    }

    if (runtimeLoading) {
        return;
    }

    runtimeLoading = true;
    runButton.disabled = true;

    setStatus("Loading Python runtime...", "running");
    setOutput(
        "Loading the AGNITI Python compiler in your browser...\n\nThis may take a few seconds on the first visit.",
        false,
        "Loading"
    );

    try {
        pyodide = await loadPyodide({
            indexURL: "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/"
        });

        await loadCompilerFiles();

        await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, "/home/pyodide")
from lexer import Lexer
from parser import Parser
from code_generator import CodeGenerator
`);

        runtimeReady = true;
        runButton.disabled = false;

        setStatus("Python runtime ready", "ready");
        setOutput(
            "Welcome to AGNITI Web IDE.\n\nPress “Run program” to execute your code.",
            false,
            "Ready"
        );

    } catch (error) {
        runtimeReady = false;
        runButton.disabled = true;

        setStatus("Python runtime failed", "error");
        setOutput(
            `Unable to start the browser Python runtime.\n\n${error.message}`,
            true,
            "Runtime error"
        );

    } finally {
        runtimeLoading = false;
    }
}


async function runInBrowser(source) {
    runtimeOutput = "";
    runtimeError = "";

    pyodide.setStdout({
        raw: value => {
            runtimeOutput += String.fromCharCode(value);
        }
    });

    pyodide.setStderr({
        raw: value => {
            runtimeError += String.fromCharCode(value);
        }
    });

    pyodide.setStdin({
        stdin: () => {
            const value = window.prompt("AGNITI input");

            if (value === null) {
                return null;
            }

            return `${value}\n`;
        }
    });

    try {
        pyodide.globals.set("AGNITI_SOURCE", source);

        await pyodide.runPythonAsync(`
source = AGNITI_SOURCE

tokens = Lexer(source).tokenize()
ast = Parser(tokens).parse()
generated_python = CodeGenerator(ast).generate()

exec(
    compile(generated_python, "<AGNITI>", "exec"),
    {}
)
`);

        return {
            output: runtimeOutput,
            error: runtimeError,
            success: true
        };

    } catch (error) {
        return {
            output: runtimeOutput,
            error: runtimeError || String(error),
            success: false
        };

    } finally {
        pyodide.setStdout({});
        pyodide.setStderr({});
        pyodide.setStdin({});
    }
}


// Runtime output buffers.
let runtimeOutput = "";
let runtimeError = "";


// Start the browser runtime immediately.
initializePythonRuntime();


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

        if (!runtimeReady) {
            setOutput(
                "Python runtime is still loading. Please wait a moment and try again.",
                true,
                "Runtime not ready"
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
            "Running AGNITI program in your browser...",
            false,
            "Running"
        );

        runTime.textContent = "—";


        const started =
            performance.now();


        try {

            const result =
                await runInBrowser(source);

            const elapsed =
                performance.now() - started;


            if (!result.success) {

                setOutput(
                    result.error || result.output || "AGNITI program failed.",
                    true,
                    "Failed"
                );

                runTime.textContent =
                    `${elapsed.toFixed(2)} ms`;

                setStatus(
                    "Execution failed",
                    "error"
                );

                return;
            }


            setOutput(
                result.output || "",
                false,
                "Finished"
            );

            runTime.textContent =
                `${elapsed.toFixed(2)} ms`;

            setStatus(
                "Program finished",
                "ready"
            );

        } catch (error) {

            setOutput(
                `Execution error: ${error.message}`,
                true,
                "Execution error"
            );

            setStatus(
                "Execution failed",
                "error"
            );

        } finally {
            runButton.disabled = !runtimeReady;
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
                "Python runtime ready",
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