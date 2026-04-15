# Design Spec: RedDragon Interactive Pipeline "Showcase"

## 1. Overview
A highly polished, attention-grabbing, single-page HTML dashboard to showcase the RedDragon architecture to stakeholders and developers. It will visualize the journey from source code compilation through the unified IR to the final execution and analysis stages.

## 2. Goals
- Deliver a "wow" factor suitable for presentations or a project README link.
- Clearly communicate the core value proposition: **Decoupling language complexity from reasoning complexity.**
- Make the "Plausible Execution" (LLM Oracle) stage feel dynamic and intelligent.

## 3. Architecture & Components

### 3.1. Layout: The "Split-Brain" Showcase UI
The application uses a modern, dark-themed UI (similar to high-end developer tools like Vercel or Linear).

*   **Left Navigation (The Pipeline):** A sticky vertical timeline representing the 4 core stages:
    1. **Source Parsing:** Multi-language inputs.
    2. **Unified Lowering:** Translating ASTs to 33-Opcode IR.
    3. **Static Analysis:** Interprocedural SCC flow.
    4. **VM & Oracle Execution:** The LLM plausible value resolution.
*   **Top Bar (The Lenses):** High-contrast toggle buttons (Process vs. Example Trace).
*   **Main Viewport:**
    *   **Process Lens (Default):** A glowing, animated SVG network diagram showing data flowing between nodes (Frontends → IR → VM → LLM).
    *   **Example Lens:** A concrete code trace. It uses side-by-side code blocks with syntax highlighting to show a "broken" Java or Haskell snippet transforming into IR, and then being resolved by the VM.

### 3.2. Attention-Grabbing Elements
- **Glowing Paths:** SVG lines in the Process view will have animated "pulses" running along them to simulate data flow.
- **Terminal Typewriter Effect:** In the Example view, the VM's interaction with the LLM Oracle will type out character-by-character to simulate real-time "thinking."
- **Smooth Transitions:** Cross-fading between the Process and Example lenses to maintain spatial awareness.
- **Syntax Highlighting:** Custom CSS to make the source code and the lowered IR look authentic and readable.

## 4. Visual Design
- **Theme:** "Deep Space" Dark Mode (Backgrounds in `#0a0a0a` to `#111`).
- **Accent Colors:**
    - Neo-Neon Blue (`#00f0ff`) for the deterministic compiler stages.
    - Electric Purple (`#b100ff`) for the LLM Oracle / "Magic" stages.
- **Typography:** 'Inter' for UI elements, 'Fira Code' (or generic monospace fallback) for code blocks.
- **Shadows:** Soft, colored drop-shadows on active pipeline stages to make them "pop."

## 5. Scope & Constraints
- **Pure Frontend:** 100% Vanilla HTML/CSS/JS in a single file (`viz/pipeline-showcase.html`). No build steps (React/Vue/Webpack) required to run it.
- **No Backend:** Pre-computed dummy data will be used for the Example Trace.
- **Zero Impact on Core:** This visualization will NOT require or introduce any changes to the `interpreter/` directory.

## 6. Implementation Steps
1. Scaffold the base HTML/CSS Grid.
2. Build the animated SVG Process flowchart.
3. Build the Example Trace code blocks with the typewriter effect.
4. Wire up the JavaScript logic for toggles and navigation scrolling.
