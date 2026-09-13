<script>
  let { template, cards, bleedMm, onset, onclear, onmany } = $props()

  let over = $state(null)     // slot index currently hovered, or 'sheet'
  let inputs = {}

  const dpi = $derived(template.dpi)
  const pw = $derived(template.page.w_px)
  const ph = $derived(template.page.h_px)
  const bleedPx = $derived((bleedMm / 25.4) * dpi)

  /** Slot geometry as percentages of the page, expanded by bleed. */
  function place(s) {
    const x = s.x - bleedPx, y = s.y - bleedPx
    const w = s.w + bleedPx * 2, h = s.h + bleedPx * 2
    return `left:${(x / pw) * 100}%;top:${(y / ph) * 100}%;` +
           `width:${(w / pw) * 100}%;height:${(h / ph) * 100}%;`
  }

  function cutBox(s) {
    return `left:${(s.x / pw) * 100}%;top:${(s.y / ph) * 100}%;` +
           `width:${(s.w / pw) * 100}%;height:${(s.h / ph) * 100}%;`
  }

  function onDropSlot(e, idx) {
    e.preventDefault(); e.stopPropagation()
    over = null
    const f = e.dataTransfer.files
    if (f.length > 1) onmany(f)
    else if (f.length === 1) onset(idx, f[0])
  }

  function onDropSheet(e) {
    e.preventDefault()
    over = null
    if (e.dataTransfer.files.length) onmany(e.dataTransfer.files)
  }
</script>

<div class="wrap"
     ondragover={(e) => { e.preventDefault(); over = over ?? 'sheet' }}
     ondragleave={() => (over = null)}
     ondrop={onDropSheet}
     class:sheetover={over === 'sheet'}
     role="region" aria-label="Card sheet">

  <div class="paper" style={`aspect-ratio:${pw}/${ph}`}>
    <!-- the real Design Space page, registration marks and all -->
    <img class="bg" src="/api/template/preview.png?guides=0" alt="" />

    {#each template.slots as s (s.index)}
      <!-- bleed area: where art actually gets painted -->
      <div class="slot" style={place(s)}
           class:over={over === s.index}
           class:has={!!cards[s.index]}
           ondragover={(e) => { e.preventDefault(); e.stopPropagation(); over = s.index }}
           ondragleave={(e) => { e.stopPropagation(); over = null }}
           ondrop={(e) => onDropSlot(e, s.index)}
           onclick={() => inputs[s.index]?.click()}
           onkeydown={(e) => e.key === 'Enter' && inputs[s.index]?.click()}
           role="button" tabindex="0"
           aria-label={`Card slot ${s.index + 1}`}>

        {#if cards[s.index]}
          <img class="art" src={cards[s.index].url} alt="" />
        {:else}
          <div class="empty">
            <span class="num">{s.index + 1}</span>
            <span class="sz">{s.w_cm} × {s.h_cm} cm</span>
            <span class="cta">drop image</span>
          </div>
        {/if}

        {#if cards[s.index]}
          <button class="x" title="Clear"
                  onclick={(e) => { e.stopPropagation(); onclear(s.index) }}>×</button>
        {/if}

        <input type="file" accept="image/*" hidden
               bind:this={inputs[s.index]}
               onchange={(e) => { onset(s.index, e.target.files[0]); e.target.value = '' }} />
      </div>

      <!-- cut line drawn on top, so you can see exactly what survives -->
      <div class="cut" style={cutBox(s)}></div>
    {/each}
  </div>

  <div class="legend">
    <span><i class="sw sw-cut"></i> cut line</span>
    <span><i class="sw sw-bleed"></i> bleed edge</span>
    <span class="tip">Drop 4 images anywhere on the sheet to fill in filename order, or one onto a card.</span>
  </div>
</div>

<style>
  .wrap {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: var(--radius); padding: 16px;
    transition: border-color .13s, background .13s;
  }
  .wrap.sheetover { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--panel)); }

  .paper {
    position: relative; width: 100%;
    background: #fff;
    border: 1px solid var(--line-bright);
    border-radius: 4px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,.25);
  }
  .bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: fill; }

  .slot {
    position: absolute;
    border: 2px dashed color-mix(in srgb, var(--bleed) 55%, transparent);
    border-radius: 2px;
    cursor: pointer;
    overflow: hidden;
    background: color-mix(in srgb, var(--bleed) 7%, transparent);
    transition: border-color .12s, background .12s, box-shadow .12s;
  }
  .slot.has { border-style: solid; background: none; }
  .slot.over {
    border-color: var(--accent); border-style: solid;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 30%, transparent);
  }
  .art { width: 100%; height: 100%; object-fit: cover; display: block; }

  .paper > .cut {
    position: absolute; pointer-events: none;
    border: 1.5px solid color-mix(in srgb, var(--cut) 85%, transparent);
    border-radius: 1px;
  }

  .empty {
    position: absolute; inset: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 3px; text-align: center; padding: 4px;
    color: #78808f;
  }
  .num { font-size: clamp(14px, 3.2vw, 26px); font-weight: 700; color: #c3cad6; line-height: 1; }
  .sz { font-size: clamp(8px, 1.2vw, 11px); font-family: ui-monospace, Menlo, monospace; }
  .cta { font-size: clamp(8px, 1.1vw, 11px); opacity: .75; }

  .x {
    position: absolute; top: 5px; right: 5px;
    width: 21px; height: 21px; padding: 0;
    display: grid; place-items: center;
    border-radius: 50%; font-size: 15px; line-height: 1;
    background: rgba(12,14,18,.72); color: #fff; border: none;
    opacity: 0; transition: opacity .12s;
  }
  .slot:hover .x { opacity: 1; }

  .legend {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    margin-top: 12px; font-size: 12px; color: var(--ink-dim);
  }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .sw { flex: none; width: 13px; height: 3px; border-radius: 2px; display: inline-block; }
  .sw-cut { background: var(--cut); }
  .sw-bleed { background: var(--bleed); }
  .tip { color: var(--ink-faint); margin-left: auto; }
  @media (max-width: 640px) { .tip { margin-left: 0; } }
</style>
