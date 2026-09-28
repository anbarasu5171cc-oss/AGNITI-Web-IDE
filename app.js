const DEFAULT_PROGRAM = 'START\n\nStep 1: Display "Hello, world!"\n\nEND';
const editor = document.getElementById('editor');
const lineNumbers = document.getElementById('line-numbers');
const output = document.getElementById('output');
const generatedPython = document.getElementById('generated-python');
const runtimeStatus = document.getElementById('runtime-status');
const runButton = document.getElementById('run-btn');
const runTime = document.getElementById('run-time');
const outputFooter = document.getElementById('output-footer');
let pyodide = null;
let deferredInstallPrompt = null;

function setStatus(message, state = '') {
  runtimeStatus.className = `status-pill ${state}`.trim();
  runtimeStatus.lastChild.textContent = message;
}
function updateLineNumbers() {
  const lines = editor.value.split('\n').length;
  lineNumbers.textContent = Array.from({length: lines}, (_, i) => i + 1).join('\n');
  document.getElementById('line-count').textContent = `${lines} line${lines === 1 ? '' : 's'}`;
  const pos = editor.selectionStart;
  const before = editor.value.slice(0, pos).split('\n');
  document.getElementById('cursor-info').textContent = `Ln ${before.length}, Col ${before[before.length - 1].length + 1}`;
  lineNumbers.scrollTop = editor.scrollTop;
}
function renumberSteps(source) {
  let count = 0;
  return source.split('\n').map(line => {
    if (/^\s*Step\s+\d+\s*:/i.test(line)) {
      count += 1;
      return line.replace(/^\s*Step\s+\d+\s*:/i, `Step ${count}:`);
    }
    return line;
  }).join('\n');
}
function setEditorValue(source, renumber = true) {
  editor.value = renumber ? renumberSteps(source) : source;
  updateLineNumbers();
}
function setOutput(text, error = false, footer = 'Finished') {
  output.textContent = text || (error ? 'Program failed without producing an error message.' : 'Program finished with no output.');
  output.classList.toggle('error', error);
  outputFooter.classList.toggle('failed', error);
  outputFooter.lastChild.textContent = footer;
}
function downloadText(filename, content, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], {type: mime});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function getFilename() {
  let name = document.getElementById('filename').value.trim() || 'untitled.agn';
  if (!name.toLowerCase().endsWith('.agn')) name += '.agn';
  return name.replace(/[\\/:*?"<>|]/g, '_');
}

editor.addEventListener('input', updateLineNumbers);
editor.addEventListener('click', updateLineNumbers);
editor.addEventListener('keyup', updateLineNumbers);
editor.addEventListener('scroll', () => { lineNumbers.scrollTop = editor.scrollTop; });
editor.addEventListener('keydown', event => {
  if (event.key === 'Tab') {
    event.preventDefault();
    const start = editor.selectionStart, end = editor.selectionEnd;
    editor.setRangeText('    ', start, end, 'end');
    updateLineNumbers();
    return;
  }
  if (event.key !== 'Enter' || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
  const start = editor.selectionStart;
  const lineStart = editor.value.lastIndexOf('\n', start - 1) + 1;
  const lineEnd = editor.value.indexOf('\n', start);
  const currentLine = editor.value.slice(lineStart, lineEnd === -1 ? editor.value.length : lineEnd);
  const stepMatch = currentLine.match(/^\s*Step\s+(\d+)\s*:/i);
  if (!stepMatch) return;
  event.preventDefault();
  const stepCount = (editor.value.match(/^\s*Step\s+\d+\s*:/gim) || []).length;
  const nextStep = stepCount + 1;
  const insert = `\nStep ${nextStep}: `;
  editor.setRangeText(insert, start, editor.selectionEnd, 'end');
  updateLineNumbers();
});

// Files are copied byte-for-byte into this separate web/compiler directory.
// The existing compiler architecture and source files are not rewritten.
async function initializeRuntime() {
  try {
    if (typeof loadPyodide !== 'function') throw new Error('Could not load Pyodide. Check your internet connection and reload this page.');
    pyodide = await loadPyodide({stdout: () => {}, stderr: () => {}});
    const compilerFiles = ['lexer.py', 'parser.py', 'code_generator.py'];
    for (const file of compilerFiles) {
      const response = await fetch(`compiler/${file}`);
      if (!response.ok) throw new Error(`Could not load compiler/${file} (HTTP ${response.status}).`);
      const content = await response.text();
      pyodide.FS.writeFile(`/home/pyodide/${file}`, content);
    }
    await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/home/pyodide')");
    // Fail fast if the compiler imports do not work in this browser runtime.
    await pyodide.runPythonAsync('from lexer import Lexer\nfrom parser import Parser\nfrom code_generator import CodeGenerator');
    runButton.disabled = false;
    setStatus('Python runtime ready', 'ready');
  } catch (error) {
    setStatus('Runtime unavailable', 'error');
    setOutput(`${error.message}\n\nThe editor still works, but Run needs the Pyodide runtime and the three compiler files in the web/compiler folder.`, true, 'Runtime unavailable');
  }
}

runButton.addEventListener('click', async () => {
  if (!pyodide) return;
  const source = editor.value.trim();
  if (!source) { setOutput('Write an AGNITI program before running.', true, 'No source'); return; }
  runButton.disabled = true;
  runButton.innerHTML = '<span class="play-icon">◌</span> Running…';
  setOutput('Compiling and running AGNITI program…', false, 'Running');
  generatedPython.textContent = 'Generating Python…';
  const start = performance.now();
  try {
    pyodide.globals.set('agniti_source_js', source);
    const pipeline = `
import contextlib, io, traceback
from lexer import Lexer
from parser import Parser
from code_generator import CodeGenerator
_agniti_stdout = io.StringIO()
_agniti_stderr = io.StringIO()
_agniti_python = ''
_agniti_error = ''
try:
    _agniti_tokens = Lexer(agniti_source_js).tokenize()
    _agniti_ast = Parser(_agniti_tokens).parse()
    _agniti_python = CodeGenerator(_agniti_ast).generate()
    with contextlib.redirect_stdout(_agniti_stdout), contextlib.redirect_stderr(_agniti_stderr):
        exec(compile(_agniti_python, '<AGNITI program>', 'exec'), {'__name__': '__main__'})
except BaseException as _e:
    _agniti_error = ''.join(traceback.format_exception_only(type(_e), _e)).strip()
_agniti_result = {
    'python': _agniti_python,
    'stdout': _agniti_stdout.getvalue(),
    'stderr': _agniti_stderr.getvalue(),
    'error': _agniti_error
}
_agniti_result
`;
    const resultProxy = await pyodide.runPythonAsync(pipeline);
    const result = resultProxy.toJs({dict_converter: Object.fromEntries});
    resultProxy.destroy();
    generatedPython.textContent = result.python || '(The compiler did not generate Python code.)';
    const elapsed = performance.now() - start;
    runTime.textContent = `${elapsed.toFixed(1)} ms`;
    const logs = [result.stdout || '', result.stderr || ''].filter(Boolean).join('\n');
    if (result.error) {
      setOutput([logs, `AGNITI/Python error: ${result.error}`].filter(Boolean).join('\n'), true, 'Execution failed');
    } else {
      setOutput(logs, false, 'Success');
    }
  } catch (error) {
    runTime.textContent = `${(performance.now() - start).toFixed(1)} ms`;
    setOutput(error?.stack || error?.message || String(error), true, 'Execution failed');
  } finally {
    runButton.disabled = false;
    runButton.innerHTML = '<span class="play-icon">▶</span> Run program';
  }
});

document.getElementById('new-btn').addEventListener('click', () => {
  if (editor.value.trim() && !confirm('Start a new program? Unsaved changes will be replaced.')) return;
  document.getElementById('filename').value = 'untitled.agn';
  setEditorValue(DEFAULT_PROGRAM);
  generatedPython.textContent = 'Generated Python will appear here after you run your program.';
  runTime.textContent = '—'; setOutput('New AGNITI program ready.', false, 'Ready'); editor.focus();
});
document.getElementById('open-btn').addEventListener('click', () => document.getElementById('file-picker').click());
document.getElementById('file-picker').addEventListener('change', async event => {
  const file = event.target.files?.[0]; if (!file) return;
  setEditorValue(await file.text());
  document.getElementById('filename').value = file.name;
  setOutput(`Opened ${file.name}`, false, 'File opened');
  event.target.value = '';
});
document.getElementById('save-btn').addEventListener('click', () => downloadText(getFilename(), editor.value));
document.getElementById('clear-btn').addEventListener('click', () => { setOutput('', false, 'Cleared'); runTime.textContent = '—'; });
document.getElementById('example-btn').addEventListener('click', () => { setEditorValue(DEFAULT_PROGRAM); editor.focus(); });

window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault(); deferredInstallPrompt = event;
  document.getElementById('install-btn').classList.remove('hidden');
});
document.getElementById('install-btn').addEventListener('click', async () => {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt(); await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null; document.getElementById('install-btn').classList.add('hidden');
});
if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
  window.addEventListener('load', () => navigator.serviceWorker.register('./service-worker.js').catch(() => {}));
}
setEditorValue(DEFAULT_PROGRAM);
initializeRuntime();
