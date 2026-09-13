<script>
  import TemplateSetup from './lib/TemplateSetup.svelte'
  import Sheet from './lib/Sheet.svelte'

  let template = $state(null)
  let loading = $state(true)
  let error = $state('')

  // slot index -> { file, url, name }
  let cards = $state({})
  let bleedMm = $state(3.2)
  let result = $state(null)
  let verify = $state(null)
  let busy = $state(false)

  const filled = $derived(Object.keys(cards).length)
  const total = $derived(template?.slots?.length ?? 0)
  const maxBleed = $derived(Math.min(6, template?.max_bleed_mm ?? 6))
  $effect(() => { if (bleedMm > maxBleed) bleedMm = maxBleed })

  async function refresh() {
    loading = true
    try {
      const r = await fetch('/api/template')
      const j = await r.json()
      template = j.loaded ? j : null
      error = j.error || ''
    } catch (e) {
      error = 'Cannot reach the server.'
    } finally {
      loading = false
    }
  }

  function setCard(idx, file) {
    if (!file || !file.type.startsWith('image/')) return
    if (cards[idx]) URL.revokeObjectURL(cards[idx].url)
    cards[idx] = { file, url: URL.createObjectURL(file), name: file.name }
    result = null; verify = null
  }

  function clearCard(idx) {
    if (cards[idx]) URL.revokeObjectURL(cards[idx].url)
    delete cards[idx]
    cards = { ...cards }
    result = null; verify = null
  }

  function clearAll() {
    for (const k of Object.keys(cards)) URL.revokeObjectURL(cards[k].url)
    cards = {}
    result = null; verify = null
  }

  /** Dropping a pile of files on the sheet fills empty slots in order,
      or every slot in order when the count matches exactly. */
  function fillMany(files) {
    const imgs = [...files].filter(f => f.type.startsWith('image/'))
                           .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    if (!imgs.length) return
    const targets = imgs.length === total
      ? template.slots.map(s => s.index)
      : template.slots.map(s => s.index).filter(i => !cards[i])
    imgs.slice(0, targets.length).forEach((f, k) => setCard(targets[k], f))
  }

  async function generate() {
    busy = true
    error = ''
    try {
      const fd = new FormData()
      const idxs = []
      for (const [k, v] of Object.entries(cards)) {
        fd.append('files', v.file, v.name)
        idxs.push(Number(k))
      }
      fd.append('slots', JSON.stringify(idxs))
      fd.append('bleed_mm', String(bleedMm))
      const r = await fetch('/api/compose', { method: 'POST', body: fd })
      if (!r.ok) throw new Error((await r.json()).detail || 'Compose failed.')
      result = await r.json()
      verify = null
      fetch(`/api/sheet/${result.id}/verify`).then(v => v.json()).then(v => (verify = v)).catch(() => {})
    } catch (e) {
      error = e.message
    } finally {
      busy = false
    }
  }

  function openPrint() {
    if (result) window.open(result.pdf, '_blank', 'noopener')
  }

  $effect(() => { refresh() })
</script>

<header>
  <div class="brand">
    <span class="dot"></span>
    <h1>cardsheet</h1>
  </div>
  {#if template}
    <div class="status">
      <span class="mono">{template.slots.length} slots</span>
      <span class="sep">·</span>
      <span class="mono">{template.slots[0].w_cm} × {template.slots[0].h_cm} cm</span>
      <span class="sep">·</span>
      <span class="mono">{template.page.w_in}″ × {template.page.h_in}″ page</span>
    </div>
  {/if}
</header>

<main>
  {#if loading}
    <p class="muted pad">Loading…</p>
  {:else if !template}
    <TemplateSetup {error} on:loaded={refresh} />
  {:else}
    <div class="cols">
      <Sheet
        {template} {cards} {bleedMm}
        onset={setCard} onclear={clearCard} onmany={fillMany}
      />

      <aside>
        <section>
          <h2>Cards</h2>
          <ol class="slots">
            {#each template.slots as s}
              <li class:done={!!cards[s.index]}>
                <span class="n">{s.index + 1}</span>
                <span class="nm">{cards[s.index]?.name ?? 'empty'}</span>
                {#if cards[s.index]}
                  <button class="sm ghost" onclick={() => clearCard(s.index)}>clear</button>
                {/if}
              </li>
            {/each}
          </ol>
          <div class="row">
            <button class="sm ghost" onclick={clearAll} disabled={!filled}>Clear all</button>
            <span class="muted mono">{filled}/{total} filled</span>
          </div>
        </section>

        <section>
          <h2>Bleed</h2>
          <div class="row">
            <input type="range" min="0" max={maxBleed} step="0.1" bind:value={bleedMm}
                   oninput={() => { result = null; verify = null }} />
            <span class="mono val">{bleedMm.toFixed(1)} mm</span>
          </div>
          <p class="hint">
            How far art extends past the cut line. Print Then Cut drifts about
            ±1 mm, so 3 mm hides it. Art gets cropped to fill card + bleed.
          </p>
          {#if template.max_bleed_mm != null && template.max_bleed_mm < 1.5}
            <div class="notice warn">
              <strong>Your cards are only {template.min_gap_mm} mm apart.</strong>
              That caps bleed at {template.max_bleed_mm} mm, below the ±1 mm this
              process drifts. Widen the gaps in the Design Space template, and check
              Bleed was OFF when you exported: Design Space's own bleed inflates the
              placeholders and eats the gap.
            </div>
          {/if}
        </section>

        <section>
          <h2>Output</h2>
          <button class="primary wide" onclick={generate}
                  disabled={busy || !filled}>
            {busy ? 'Building…' : result ? 'Rebuild sheet' : 'Build sheet'}
          </button>

          {#if result}
            <div class="row gap">
              <button class="primary wide" onclick={openPrint}>Open &amp; print</button>
              <a class="btnlink" href={`${result.pdf}?download=1`} download>Download</a>
            </div>
            {#if verify}
              <div class="notice {verify.ok ? 'good' : 'warn'}">
                {#if verify.ok}
                  <strong>Registration marks verified.</strong>
                  All {verify.mark_pixels.toLocaleString()} mark pixels are identical to
                  your template, page still {verify.page_pt[0]} × {verify.page_pt[1]} pt.
                {:else}
                  <strong>Mark check failed.</strong>
                  {verify.reason ?? `${verify.mark_pixels_changed} mark pixels changed`}. Do not print this.
                {/if}
              </div>
            {/if}
            <div class="notice">
              <strong>Print at 100% scale.</strong> No “fit to page”, no
              auto-rotate, portrait, {template.page.w_in}″ × {template.page.h_in}″ paper.
              Rescaling moves the registration marks and the cut lands off.
            </div>
          {/if}

          {#each result?.warnings ?? [] as w}
            <div class="notice warn">{w}</div>
          {/each}
          {#if error}<div class="notice err">{error}</div>{/if}
        </section>

        <section>
          <h2>Template</h2>
          <p class="hint mono">{template.filename}</p>
          <p class="hint">Uploaded {template.uploaded_at}</p>
          <button class="sm ghost" onclick={async () => {
            if (!confirm('Remove the template? You will need to re-upload the Design Space PDF.')) return
            await fetch('/api/template', { method: 'DELETE' }); clearAll(); refresh()
          }}>Replace template</button>
        </section>
      </aside>
    </div>
  {/if}
</main>

<style>
  header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; flex-wrap: wrap;
    padding: 14px 20px;
    border-bottom: 1px solid var(--line);
    background: var(--panel);
  }
  .brand { display: flex; align-items: center; gap: 9px; }
  .dot {
    width: 10px; height: 10px; border-radius: 3px;
    background: var(--cut); box-shadow: 0 0 0 3px color-mix(in srgb, var(--cut) 22%, transparent);
  }
  .status { display: flex; align-items: center; gap: 8px; color: var(--ink-dim); font-size: 12px; }
  .sep { color: var(--ink-faint); }

  main { padding: 20px; max-width: 1400px; margin: 0 auto; }
  .pad { padding: 40px 0; }
  .muted { color: var(--ink-dim); }

  .cols { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 20px; align-items: start; }
  @media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }

  aside { display: flex; flex-direction: column; gap: 14px; }
  section {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: var(--radius); padding: 14px;
  }
  section > h2 { margin-bottom: 10px; }

  .slots { list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; gap: 5px; }
  .slots li {
    display: flex; align-items: center; gap: 9px;
    padding: 6px 9px; border-radius: 7px;
    background: var(--panel-2); border: 1px solid transparent;
    font-size: 12px;
  }
  .slots li.done { border-color: color-mix(in srgb, var(--cut) 45%, transparent); }
  .n {
    width: 19px; height: 19px; flex: none; border-radius: 5px;
    display: grid; place-items: center;
    background: var(--line); color: var(--ink-dim);
    font-size: 11px; font-weight: 600;
  }
  .slots li.done .n { background: var(--cut); color: #06231a; }
  .nm {
    flex: 1; min-width: 0; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
    font-family: ui-monospace, Menlo, Consolas, monospace;
  }
  .slots li:not(.done) .nm { color: var(--ink-faint); }

  .row { display: flex; align-items: center; gap: 10px; }
  .row.gap { margin-top: 9px; }
  .row input[type=range] { flex: 1; }
  .val { flex: none; width: 56px; text-align: right; color: var(--ink-dim); }

  .wide { width: 100%; }
  .btnlink {
    display: inline-grid; place-items: center;
    padding: 8px 14px; border-radius: 8px; text-decoration: none;
    border: 1px solid var(--line-bright); background: var(--panel-2); color: var(--ink);
    font-size: 14px; white-space: nowrap;
  }
  .btnlink:hover { background: var(--line); }

  .hint { color: var(--ink-faint); font-size: 12px; margin: 8px 0 0; }
  .notice {
    margin-top: 10px; padding: 9px 11px; border-radius: 7px;
    font-size: 12px; line-height: 1.45;
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    color: var(--ink);
  }
  .notice.warn {
    background: color-mix(in srgb, var(--warn) 14%, transparent);
    border-color: color-mix(in srgb, var(--warn) 40%, transparent);
  }
  .notice.good {
    background: color-mix(in srgb, var(--cut) 13%, transparent);
    border-color: color-mix(in srgb, var(--cut) 40%, transparent);
  }
  .notice.err {
    background: color-mix(in srgb, var(--err) 14%, transparent);
    border-color: color-mix(in srgb, var(--err) 40%, transparent);
  }
</style>
