<script>
  let { error = '' } = $props()
  const dispatch = (name) => el?.dispatchEvent(new CustomEvent(name, { bubbles: true }))

  let el
  let input
  let busy = $state(false)
  let msg = $state('')
  let over = $state(false)

  async function upload(file) {
    if (!file) return
    busy = true
    msg = ''
    try {
      const fd = new FormData()
      fd.append('file', file, file.name)
      const r = await fetch('/api/template', { method: 'POST', body: fd })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'Upload failed.')
      dispatch('loaded')
    } catch (e) {
      msg = e.message
    } finally {
      busy = false
    }
  }
</script>

<div class="setup" bind:this={el}>
  <div class="drop"
       class:over
       class:busy
       ondragover={(e) => { e.preventDefault(); over = true }}
       ondragleave={() => (over = false)}
       ondrop={(e) => { e.preventDefault(); over = false; upload(e.dataTransfer.files[0]) }}
       onclick={() => input.click()}
       onkeydown={(e) => e.key === 'Enter' && input.click()}
       role="button" tabindex="0">
    <div class="icon">PDF</div>
    <h3>{busy ? 'Reading template…' : 'Drop your Design Space template PDF'}</h3>
    <p>The print-to-PDF export with the magenta placeholder rectangles.</p>
    <input type="file" accept="application/pdf" hidden bind:this={input}
           onchange={(e) => { upload(e.target.files[0]); e.target.value = '' }} />
  </div>

  {#if msg || error}<div class="err">{msg || error}</div>{/if}

  <div class="how">
    <h2>Making that PDF, once</h2>
    <ol>
      <li>Upload <code>template_2x2_63x88mm_letter.svg</code> to Design Space.</li>
      <li>Set units to cm, confirm each card reads <strong>6.3 × 8.8</strong>.</li>
      <li>Set all four rectangles to <strong>Print Then Cut</strong>.</li>
      <li>Select all four and <strong>Attach</strong>, so Design Space cannot rearrange them.</li>
      <li><strong>Save the project.</strong> This is what you reopen for every cut.</li>
      <li>Make It → Print Setup → <strong>Bleed OFF</strong> → Send to Printer →
          <strong>Save as PDF</strong>. Then cancel out of the cut step.</li>
      <li>Drop that PDF above. It is stored in the container volume, so you only
          do this once.</li>
    </ol>
    <p class="note">
      Bleed must be off. Design Space's own bleed fuzzes the edge of the
      placeholder and shifts where the cut line gets detected.
    </p>
  </div>
</div>

<style>
  .setup { max-width: 640px; margin: 24px auto; display: flex; flex-direction: column; gap: 18px; }

  .drop {
    border: 2px dashed var(--line-bright);
    border-radius: 14px;
    padding: 44px 24px;
    text-align: center;
    cursor: pointer;
    background: var(--panel);
    transition: border-color .14s, background .14s;
  }
  .drop:hover, .drop.over {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 7%, var(--panel));
  }
  .drop.busy { opacity: .6; pointer-events: none; }
  .icon {
    width: 46px; height: 46px; margin: 0 auto 14px;
    display: grid; place-items: center;
    border-radius: 10px; background: var(--panel-2); border: 1px solid var(--line-bright);
    font-size: 11px; font-weight: 700; letter-spacing: .04em; color: var(--ink-dim);
  }
  .drop h3 { font-size: 15px; margin-bottom: 5px; }
  .drop p { margin: 0; color: var(--ink-faint); font-size: 13px; }

  .err {
    padding: 10px 12px; border-radius: 8px; font-size: 13px;
    background: color-mix(in srgb, var(--err) 14%, transparent);
    border: 1px solid color-mix(in srgb, var(--err) 40%, transparent);
  }

  .how {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: var(--radius); padding: 16px 18px;
  }
  .how h2 { margin-bottom: 10px; }
  .how ol { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 7px; }
  .how li { font-size: 13px; color: var(--ink-dim); }
  .how li strong { color: var(--ink); }
  .how code {
    background: var(--panel-2); padding: 1px 5px; border-radius: 4px;
    border: 1px solid var(--line); color: var(--ink);
  }
  .note {
    margin: 14px 0 0; padding: 9px 11px; border-radius: 7px; font-size: 12px;
    background: color-mix(in srgb, var(--warn) 13%, transparent);
    border: 1px solid color-mix(in srgb, var(--warn) 38%, transparent);
    color: var(--ink);
  }
</style>
