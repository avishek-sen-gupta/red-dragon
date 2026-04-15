# RedDragon Interactive Showcase Implementation Plan

> **For agentic workers:** Execute this plan inline. DO NOT modify any files in `interpreter/`.

**Goal:** Build a highly polished, attention-grabbing HTML dashboard to showcase the RedDragon compilation-to-analysis pipeline.

**Architecture:** A single-page web app with smooth CSS transitions, SVG animations, and a "typewriter" effect to visualize the LLM Oracle.

**Tech Stack:** Vanilla HTML5, CSS3, JavaScript.

---

### Task 1: Scaffolding and "Deep Space" Base Theme

**Files:**
- Create: `viz/pipeline-showcase.html`

- [ ] **Step 1: Write the HTML skeleton with CSS Grid and Neon variables**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RedDragon Pipeline Showcase</title>
    <style>
        :root {
            --bg-color: #0a0a0a;
            --panel-bg: #111111;
            --text-main: #e0e0e0;
            --text-muted: #888888;
            --neon-blue: #00f0ff;
            --neon-purple: #b100ff;
            --code-bg: #1e1e1e;
            --border-color: #333333;
        }

        body {
            margin: 0;
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            display: grid;
            grid-template-columns: 300px 1fr;
            height: 100vh;
            overflow: hidden;
        }

        /* Sidebar Styling */
        #sidebar {
            background-color: var(--panel-bg);
            border-right: 1px solid var(--border-color);
            padding: 30px 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            z-index: 10;
        }

        .brand-title {
            font-size: 24px;
            font-weight: 800;
            margin-bottom: 20px;
            background: linear-gradient(90deg, var(--neon-blue), var(--neon-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .stage-card {
            padding: 15px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .stage-card:hover {
            border-color: var(--text-muted);
        }

        .stage-card.active {
            border-color: var(--neon-blue);
            background: rgba(0, 240, 255, 0.05);
            box-shadow: 0 0 15px rgba(0, 240, 255, 0.2);
        }

        .stage-card.active-oracle {
            border-color: var(--neon-purple);
            background: rgba(177, 0, 255, 0.05);
            box-shadow: 0 0 15px rgba(177, 0, 255, 0.2);
        }

        /* Main Viewport */
        #main-content {
            display: flex;
            flex-direction: column;
            position: relative;
        }

        #header-controls {
            padding: 20px 40px;
            display: flex;
            justify-content: flex-end;
            border-bottom: 1px solid var(--border-color);
            background: var(--panel-bg);
            z-index: 10;
        }

        .toggle-btn {
            background: transparent;
            color: var(--text-muted);
            border: 1px solid var(--border-color);
            padding: 10px 20px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            transition: all 0.3s;
        }

        .toggle-btn:first-child { border-radius: 6px 0 0 6px; border-right: none; }
        .toggle-btn:last-child { border-radius: 0 6px 6px 0; }

        .toggle-btn.active {
            background: rgba(0, 240, 255, 0.1);
            color: var(--neon-blue);
            border-color: var(--neon-blue);
            box-shadow: inset 0 0 10px rgba(0, 240, 255, 0.2);
        }

        #viewport-container {
            flex: 1;
            position: relative;
            overflow: hidden;
        }

        /* View Panels */
        .view-panel {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            padding: 40px;
            overflow-y: auto;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.5s ease;
        }

        .view-panel.visible {
            opacity: 1;
            visibility: visible;
        }
    </style>
</head>
<body>
    <div id="sidebar">
        <div class="brand-title">RedDragon</div>
        <div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">Pipeline Architecture</div>
        
        <div class="stage-card active" data-target="stage-1">
            <strong style="color: #fff;">1. Source Inputs</strong>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 5px;">15+ Language Frontends</div>
        </div>
        <div class="stage-card" data-target="stage-2">
            <strong style="color: #fff;">2. Unified Lowering</strong>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 5px;">33-Opcode IR Generation</div>
        </div>
        <div class="stage-card" data-target="stage-3">
            <strong style="color: #fff;">3. Static Analysis</strong>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 5px;">SCC Fixpoint & Dataflow</div>
        </div>
        <div class="stage-card" data-target="stage-4" id="card-oracle">
            <strong style="color: #fff;">4. Execution Oracle</strong>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 5px;">LLM Plausible Resolution</div>
        </div>
    </div>

    <div id="main-content">
        <div id="header-controls">
            <div>
                <button class="toggle-btn active" id="btn-process">Process Flow</button>
                <button class="toggle-btn" id="btn-example">Live Trace</button>
            </div>
        </div>
        <div id="viewport-container">
            <div id="view-process" class="view-panel visible">
                <!-- SVG diagram goes here -->
                <h2 style="color: var(--neon-blue); font-weight: 300;">Universal Abstraction Architecture</h2>
            </div>
            <div id="view-example" class="view-panel">
                <!-- Code trace goes here -->
                <h2 style="color: var(--neon-purple); font-weight: 300;">Example Execution Trace</h2>
            </div>
        </div>
    </div>
</body>
</html>
```

---

### Task 2: Animated SVG Process Flow Diagram

**Files:**
- Modify: `viz/pipeline-showcase.html`

- [ ] **Step 1: Add the SVG diagram with pulsing paths to `#view-process`**

```html
<!-- Replace content of #view-process -->
<h2 style="color: var(--neon-blue); font-weight: 300;">Universal Abstraction Architecture</h2>
<p style="color: var(--text-muted); max-width: 600px; line-height: 1.6; margin-bottom: 40px;">
    RedDragon decouples language complexity from reasoning complexity. By lowering all code to a common, typed IR, the analysis engine treats diverse languages with identical mathematical rigor.
</p>

<svg width="100%" height="450" viewBox="0 0 900 450" style="background: rgba(255,255,255,0.01); border-radius: 12px; border: 1px solid var(--border-color);">
    <defs>
        <!-- Glow Filters -->
        <filter id="glow-blue" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <filter id="glow-purple" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>

        <!-- Gradients -->
        <linearGradient id="grad-blue" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#111" />
            <stop offset="100%" stop-color="var(--neon-blue)" stop-opacity="0.3"/>
        </linearGradient>
    </defs>

    <!-- Base Paths -->
    <path d="M 200 150 L 350 150" stroke="#333" stroke-width="3" fill="none" />
    <path d="M 500 150 L 650 100" stroke="#333" stroke-width="3" fill="none" />
    <path d="M 500 150 L 650 250" stroke="#333" stroke-width="3" fill="none" />
    <path d="M 650 250 L 800 250" stroke="#333" stroke-width="3" stroke-dasharray="6,6" fill="none" />

    <!-- Animated Data Pulses (CSS styling needed) -->
    <path class="pulse-path" d="M 200 150 L 350 150" stroke="var(--neon-blue)" stroke-width="4" fill="none" stroke-dasharray="20 150" />
    <path class="pulse-path delay-1" d="M 500 150 L 650 100" stroke="var(--neon-blue)" stroke-width="4" fill="none" stroke-dasharray="20 180" />
    <path class="pulse-path delay-2" d="M 500 150 L 650 250" stroke="var(--neon-blue)" stroke-width="4" fill="none" stroke-dasharray="20 180" />
    
    <!-- Nodes -->
    <!-- Frontends -->
    <rect x="50" y="110" width="150" height="80" rx="8" fill="#1a1a1a" stroke="var(--border-color)" stroke-width="2" />
    <text x="125" y="145" text-anchor="middle" fill="#fff" font-family="Inter" font-weight="600">Frontends</text>
    <text x="125" y="165" text-anchor="middle" fill="#888" font-family="Inter" font-size="12">AST Parsing</text>

    <!-- Unified IR -->
    <rect x="350" y="110" width="150" height="80" rx="8" fill="url(#grad-blue)" stroke="var(--neon-blue)" stroke-width="2" filter="url(#glow-blue)" />
    <text x="425" y="145" text-anchor="middle" fill="#fff" font-family="Inter" font-weight="600">Unified IR</text>
    <text x="425" y="165" text-anchor="middle" fill="var(--neon-blue)" font-family="Inter" font-size="12">33-Opcode Core</text>

    <!-- Analysis -->
    <rect x="650" y="60" width="150" height="80" rx="8" fill="#1a1a1a" stroke="var(--border-color)" stroke-width="2" />
    <text x="725" y="95" text-anchor="middle" fill="#fff" font-family="Inter" font-weight="600">Static Analysis</text>
    <text x="725" y="115" text-anchor="middle" fill="#888" font-family="Inter" font-size="12">Dataflow Graph</text>

    <!-- VM -->
    <rect x="650" y="210" width="150" height="80" rx="8" fill="#1a1a1a" stroke="var(--border-color)" stroke-width="2" />
    <text x="725" y="245" text-anchor="middle" fill="#fff" font-family="Inter" font-weight="600">VM Engine</text>
    <text x="725" y="265" text-anchor="middle" fill="#888" font-family="Inter" font-size="12">Execution Oracle</text>

    <!-- LLM Oracle -->
    <rect x="750" y="320" width="130" height="60" rx="8" fill="rgba(177,0,255,0.1)" stroke="var(--neon-purple)" stroke-width="2" filter="url(#glow-purple)" />
    <path d="M 725 290 L 815 320" stroke="var(--neon-purple)" stroke-width="2" fill="none" stroke-dasharray="4,4" />
    <text x="815" y="345" text-anchor="middle" fill="#fff" font-family="Inter" font-weight="600">LLM Resolver</text>
    <text x="815" y="365" text-anchor="middle" fill="var(--neon-purple)" font-family="Inter" font-size="11">Plausible Return Values</text>
</svg>
```

- [ ] **Step 2: Add SVG animation CSS**

```css
/* Add to <style> inside <head> */
.pulse-path {
    stroke-dashoffset: 200;
    animation: dash 3s linear infinite;
}
.delay-1 { animation-delay: 1s; }
.delay-2 { animation-delay: 1.5s; }

@keyframes dash {
    from { stroke-dashoffset: 200; }
    to { stroke-dashoffset: 0; }
}
```

---

### Task 3: Code Trace and Typewriter Effect

**Files:**
- Modify: `viz/pipeline-showcase.html`

- [ ] **Step 1: Add Trace layout and Typewriter CSS to `<style>`**

```css
/* Add to <style> inside <head> */
.trace-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 30px;
    margin-top: 30px;
}
.code-window {
    background: var(--code-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    margin-bottom: 20px;
    opacity: 0.3;
    transition: opacity 0.5s ease, border-color 0.3s ease;
}
.code-window.active-trace {
    opacity: 1;
    border-color: var(--neon-blue);
}
.code-window.oracle-trace {
    opacity: 1;
    border-color: var(--neon-purple);
}
.window-header {
    background: #151515;
    padding: 10px 15px;
    font-size: 11px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border-color);
    text-transform: uppercase;
    letter-spacing: 1px;
    display: flex;
    justify-content: space-between;
}
.window-body {
    padding: 20px;
    font-family: 'Fira Code', 'Consolas', monospace;
    font-size: 14px;
    line-height: 1.6;
    color: #ccc;
    white-space: pre-wrap;
}

/* Typewriter cursor */
.typewriter-text::after {
    content: '▋';
    animation: blink 1s step-start infinite;
    color: var(--neon-purple);
}
@keyframes blink { 50% { opacity: 0; } }

/* Syntax */
.kw { color: #569cd6; } /* Keyword */
.fn { color: #dcdcaa; } /* Function */
.str { color: #ce9178; } /* String */
.ir-op { color: #c586c0; } /* IR Opcode */
.ir-reg { color: #9cdcfe; } /* IR Register */
```

- [ ] **Step 2: Add Example View HTML**

```html
<!-- Replace content of #view-example -->
<div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 20px;">
    <div>
        <h2 style="color: var(--neon-purple); font-weight: 300; margin-bottom: 10px;">Example Execution Trace</h2>
        <p style="color: var(--text-muted); max-width: 600px; line-height: 1.6; margin: 0;">
            Watch how a Java snippet containing an unresolved external call is lowered, analyzed, and dynamically resolved via the LLM Oracle.
        </p>
    </div>
</div>

<div class="trace-grid">
    <!-- Left Column: Source and IR -->
    <div>
        <!-- Stage 1 -->
        <div class="code-window active-trace" id="trace-1">
            <div class="window-header"><span>Java Source</span> <span>Stage 1</span></div>
            <div class="window-body">
<span class="kw">public void</span> <span class="fn">processData</span>(User user) {
  <span class="kw">String</span> json = externalApi.<span class="fn">fetch</span>(user);
  <span class="kw">this</span>.<span class="fn">save</span>(json);
}</div>
        </div>

        <!-- Stage 2 -->
        <div class="code-window" id="trace-2">
            <div class="window-header"><span style="color: var(--neon-blue);">Unified TAC IR</span> <span>Stage 2</span></div>
            <div class="window-body">
<span class="ir-reg">%r1</span> = <span class="ir-op">load_var</span> user
<span class="ir-reg">%r2</span> = <span class="ir-op">load_var</span> externalApi
<span class="ir-reg">%r3</span> = <span class="ir-op">call_method</span> <span class="ir-reg">%r2</span> fetch <span class="ir-reg">%r1</span>
<span class="ir-reg">%r4</span> = <span class="ir-op">load_var</span> this
<span class="ir-op">call_method</span> <span class="ir-reg">%r4</span> save <span class="ir-reg">%r3</span></div>
        </div>
    </div>

    <!-- Right Column: VM and Oracle -->
    <div>
        <!-- Stage 3 & 4 -->
        <div class="code-window" id="trace-3-4" style="height: calc(100% - 20px);">
            <div class="window-header"><span>VM Execution & Oracle</span> <span>Stage 3 & 4</span></div>
            <div class="window-body" id="vm-console" style="color: #4af626;">
> Initializing VM State...
> Executing: <span class="ir-reg">%r3</span> = <span class="ir-op">call_method</span> <span class="ir-reg">%r2</span> fetch <span class="ir-reg">%r1</span>
<span style="color: #f44;">[!] Error: 'externalApi.fetch' unresolved.</span>
> Pausing static execution.
> Querying LLM Resolver for plausible return value...
<br><br>
<span id="oracle-output" style="color: var(--neon-purple); font-weight: bold; display: none;">> Oracle: <span class="str typewriter-text" id="typewriter"></span></span>
<br>
<span id="vm-resume" style="display: none;">
> Binding <span class="ir-reg">%r3</span> = <span class="str">"{id: 42, status: 'ok'}"</span>
> Resuming execution: <span class="ir-op">call_method</span> <span class="ir-reg">%r4</span> save <span class="ir-reg">%r3</span>
> <span style="color: #fff;">Dataflow verified.</span>
</span>
            </div>
        </div>
    </div>
</div>
```

---

### Task 4: Interactive JavaScript Logic

**Files:**
- Modify: `viz/pipeline-showcase.html`

- [ ] **Step 1: Add Script to handle view toggles and sidebar staging**

```html
<!-- Add just before </body> -->
<script>
    // View Toggles
    const btnProcess = document.getElementById('btn-process');
    const btnExample = document.getElementById('btn-example');
    const viewProcess = document.getElementById('view-process');
    const viewExample = document.getElementById('view-example');

    btnProcess.addEventListener('click', () => {
        btnProcess.classList.add('active');
        btnExample.classList.remove('active');
        viewProcess.classList.add('visible');
        viewExample.classList.remove('visible');
    });

    btnExample.addEventListener('click', () => {
        btnExample.classList.add('active');
        btnProcess.classList.remove('active');
        viewExample.classList.add('visible');
        viewProcess.classList.remove('visible');
    });

    // Sidebar & Trace Highlighting
    const stageCards = document.querySelectorAll('.stage-card');
    const trace1 = document.getElementById('trace-1');
    const trace2 = document.getElementById('trace-2');
    const trace34 = document.getElementById('trace-3-4');
    
    // Typewriter state
    const typewriterEl = document.getElementById('typewriter');
    const oracleOutput = document.getElementById('oracle-output');
    const vmResume = document.getElementById('vm-resume');
    const oracleText = '"{id: 42, status: \'ok\'}"';
    let typeTimeout = null;

    function resetTypewriter() {
        clearTimeout(typeTimeout);
        typewriterEl.textContent = '';
        oracleOutput.style.display = 'none';
        vmResume.style.display = 'none';
        trace34.classList.remove('oracle-trace', 'active-trace');
    }

    function runTypewriter() {
        oracleOutput.style.display = 'inline';
        let i = 0;
        function typeWriter() {
            if (i < oracleText.length) {
                typewriterEl.textContent += oracleText.charAt(i);
                i++;
                typeTimeout = setTimeout(typeWriter, 50); // Speed
            } else {
                setTimeout(() => {
                    typewriterEl.classList.remove('typewriter-text');
                    vmResume.style.display = 'block';
                }, 500);
            }
        }
        typeWriter();
    }

    stageCards.forEach(card => {
        card.addEventListener('click', () => {
            // Update Sidebar
            stageCards.forEach(c => {
                c.classList.remove('active', 'active-oracle');
            });
            
            const target = card.getAttribute('data-target');
            if (target === 'stage-4') {
                card.classList.add('active-oracle');
            } else {
                card.classList.add('active');
            }

            // Switch to example view to show the trace
            if (!btnExample.classList.contains('active')) {
                btnExample.click();
            }

            // Reset Trace States
            trace1.classList.remove('active-trace');
            trace2.classList.remove('active-trace');
            resetTypewriter();

            // Apply specific stage logic
            if (target === 'stage-1') {
                trace1.classList.add('active-trace');
            } 
            else if (target === 'stage-2') {
                trace1.classList.add('active-trace');
                trace2.classList.add('active-trace');
            } 
            else if (target === 'stage-3') {
                trace1.classList.add('active-trace');
                trace2.classList.add('active-trace');
                trace34.classList.add('active-trace');
                oracleOutput.style.display = 'none'; // Only show error
            } 
            else if (target === 'stage-4') {
                trace1.classList.add('active-trace');
                trace2.classList.add('active-trace');
                trace34.classList.add('oracle-trace');
                typewriterEl.classList.add('typewriter-text');
                runTypewriter();
            }
        });
    });
</script>
```

- [ ] **Step 2: Save the file.**
