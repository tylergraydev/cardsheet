<script>
  let files = $state([])          // { file, url, name }
  let gapMm = $state(3)
  let borderMm = $state(0.9)
  let addBorder = $state(true)
  let dieCut = $state('auto')
  let split = $state('auto')
  let smooth = $state(0.6)
  let busy = $state(false)
  let error = $state('')
  let result = $state(null)
  let over = $state(false)

  function add(list) {
    for (const f of list) {
      if (!f.type.startsWith('image/')) continue
      files.push({ file: f, url: URL.createObjectURL(f), name: f.name })
    }
    result = null
  }

  function remove(i) {
    URL.revokeObjectURL(files[i].url)
    files.splice(i, 1)
    result = null
  }

  function clearAll() {
    for (const f of files) URL.revokeObjectURL(f.url)
    files = []
    result = null
  }

  async function pack() {
    if (!files.length) return
    busy = true; error = ''; result = null
    const fd = new FormData()
    for (const f of files) fd.append('files', f.file, f.name)
    fd.append('gap_mm', String(gapMm))
    fd.append('border_mm', String(borderMm))
    fd.append('add_border', String(addBorder))
    fd.append('die_cut', dieCut)
    fd.append('split', split)
    fd.append('smooth', String(smooth))
    try {
      const r = await fetch('/api/stickers/pack', { method: 'POST', body: fd })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || 'Packing failed.')
      result = j
    } catch (e) {
      error = e.message || 'Packing failed.'
    } finally {
      busy = false
    }
  }
</script>

<div class="cols">
  <div class="pane">
    {#if result}
      <img class="layout" src={result.preview} alt="Packed sticker layout" />
    {:else}
      <div class="drop"
           class:over
           role="button" tabindex="0"
           ondragover={(e) => { e.preventDefault(); over = true }}
           ondragleave={() => (over = false)}
           ondrop={(e) => { e.preventDefault(); over = false; add(e.dataTransfer.files) }}
           onclick={() => document.getElementById('stk-input').click()}
           onkeydown={(e) => e.key === 'Enter' && document.getElementById('stk-input').click()}>
        {#if files.length}
          <div class="thumbs">
            {#each files as f, i}
              <div class="thumb">
                <img src={f.url} alt={f.name} />
                <button class="x" title="Remove"
                        onclick={(e) => { e.stopPropagation(); remove(i) }}>×</button>
              </div>
            {/each}
          </div>
        {:else}
          <div class="empty">
            <strong>Drop sticker images here</strong>
            <span class="muted">Any number, any shape. Transparent art is die-cut.</span>
            <span class="muted">One sheet with several stickers on it works too,
              it gets split automatically.</span>
          </div>
        {/if}
      </div>
    {/if}
    <input id="stk-input" type="file" accept="image/*" multiple hidden
           onchange={(e) => { add(e.target.files); e.target.value = '' }} />
  </div>

  <aside>
    <section>
      <h2>Stickers</h2>
      <p class="hint">
        {files.length} loaded. Each one is packed to the same area, as large as
        the sheet allows, so they all come out looking the same size.
      </p>
      {#if files.length}
        <button class="wide" onclick={clearAll}>Clear all</button>
      {/if}
    </section>

    {#if files.length === 1}
      <section>
        <h2>Sheet</h2>
        <select bind:value={split} onchange={() => (result = null)}>
          <option value="auto">Split it into separate stickers</option>
          <option value="no">It is one single sticker</option>
        </select>
        <p class="hint">One transparent image holding several stickers is cut
          apart on the gaps between them, then each piece is packed on its own.</p>
      </section>
    {/if}

    <section>
      <h2>Spacing</h2>
      <div class="row">
        <input type="range" min="1" max="10" step="0.5" bind:value={gapMm}
               oninput={() => (result = null)} />
        <span class="mono val">{gapMm} mm</span>
      </div>
      <p class="hint">Gap between stickers. The cut drifts about ±1 mm, so 3 mm
        is a sensible floor.</p>
    </section>

    <section>
      <h2>Border</h2>
      <label class="check">
        <input type="checkbox" bind:checked={addBorder}
               onchange={() => (result = null)} />
        Add a rim to art that has none
      </label>
      {#if addBorder}
        <div class="row">
          <input type="range" min="0.3" max="3" step="0.1" bind:value={borderMm}
                 oninput={() => (result = null)} />
          <span class="mono val">{borderMm} mm</span>
        </div>
        <div class="row">
          <input type="range" min="0" max="1.5" step="0.1" bind:value={smooth}
                 oninput={() => (result = null)} />
          <span class="mono val">{smooth === 0 ? 'sharp' : smooth.toFixed(1) + '×'}</span>
        </div>
        <p class="hint">Smoothing rounds the rim off instead of tracing every
          jag in the artwork. It fills notches narrower than about twice this,
          measured in rim widths.</p>
      {/if}
      <p class="hint">Art that already has a white rim is detected and left
        alone, so this only affects bare artwork.</p>
    </section>

    <section>
      <h2>Cut</h2>
      <select bind:value={dieCut} onchange={() => (result = null)}>
        <option value="auto">Auto: die-cut when the art is transparent</option>
        <option value="yes">Always die-cut the silhouette</option>
        <option value="no">Always cut rectangles</option>
      </select>
    </section>

    <section>
      <h2>Output</h2>
      <button class="primary wide" onclick={pack} disabled={busy || !files.length}>
        {busy ? 'Packing…' : 'Pack the sheet'}
      </button>

      {#if error}<div class="notice err">{error}</div>{/if}

      {#if result}
        <div class="stats mono">
          <div>{result.count} stickers, {result.die_cut ? 'die-cut' : 'rectangular'}</div>
          <div>{result.typical_mm} × {result.typical_mm} mm typical</div>
          <div>{result.group_mm[0]} × {result.group_mm[1]} mm group</div>
          <div>{result.dpi[0]}–{result.dpi[1]} dpi</div>
          {#if result.rotated}<div>{result.rotated} rotated to fit</div>{/if}
        </div>
        {#each result.notes as n}<p class="hint">{n}</p>{/each}

        {#if result.dpi[0] < 150}
          <div class="notice warn">
            <strong>{result.dpi[0]} dpi is low.</strong>
            The art is being enlarged past what it holds. Fewer stickers per
            sheet will not help, smaller ones will.
          </div>
        {/if}

        <a class="btn wide" href={result.sheet} download>
          Download print-ready sheet (PNG)
        </a>
        <p class="hint">Upload that to Design Space and set it to
          {result.group_mm[0]} × {result.group_mm[1]} mm. It traces the cut line
          from the transparency itself.</p>

        <a class="btn wide" href={result.svg} download>
          Download magenta template (SVG)
        </a>
        <p class="hint">The other route: cut this in Design Space, print to PDF,
          and load it as a cardsheet template instead.</p>
      {/if}
    </section>
  </aside>
</div>

<style>
  .cols { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 24px; }
  @media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }

  .pane { min-width: 0; }
  .layout {
    width: 100%; height: auto; display: block; border-radius: 6px;
    border: 1px solid var(--line, #ddd); background: #fff;
  }
  .drop {
    min-height: 420px; border: 2px dashed var(--line, #ccc); border-radius: 8px;
    display: flex; align-items: center; justify-content: center; cursor: pointer;
    padding: 16px; transition: border-color .12s, background .12s;
  }
  .drop.over { border-color: var(--accent, #c0f); background: rgba(204, 0, 255, .05); }
  .empty { display: flex; flex-direction: column; gap: 6px; text-align: center; }

  .thumbs {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
    gap: 10px; width: 100%; align-self: flex-start;
  }
  .thumb { position: relative; aspect-ratio: 1; }
  .thumb img { width: 100%; height: 100%; object-fit: contain; }
  .thumb .x {
    position: absolute; top: -6px; right: -6px; width: 20px; height: 20px;
    border-radius: 50%; border: none; cursor: pointer; line-height: 1;
    background: rgba(0, 0, 0, .6); color: #fff;
  }

  .row { display: flex; align-items: center; gap: 10px; }
  .row input[type=range] { flex: 1; }
  .val { min-width: 58px; text-align: right; }
  .check { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  select { width: 100%; padding: 6px; }

  .stats { font-size: 12px; line-height: 1.7; margin: 10px 0; opacity: .85; }
  .btn {
    display: block; text-align: center; padding: 9px; margin-top: 10px;
    border: 1px solid var(--line, #ccc); border-radius: 5px; text-decoration: none;
    color: inherit;
  }
  .btn:hover { border-color: var(--accent, #c0f); }
  .wide { width: 100%; }
</style>
