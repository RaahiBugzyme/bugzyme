import { memo } from 'react'

const illustration = String.raw`<svg class="couple-svg" viewBox="0 0 340 200" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- GLOW under bench -->
      <ellipse cx="170" cy="188" rx="90" ry="10" fill="rgba(168,85,247,.18)"/>

      <!-- ─── BENCH ────────────────────────────── -->
      <g class="bench-glow">
        <!-- seat plank -->
        <rect x="62" y="148" width="218" height="13" rx="6" fill="#3b1f6a"/>
        <rect x="62" y="148" width="218" height="5" rx="3" fill="#5a2f9e"/>
        <!-- legs -->
        <rect x="78"  y="161" width="10" height="28" rx="4" fill="#3b1f6a"/>
        <rect x="254" y="161" width="10" height="28" rx="4" fill="#3b1f6a"/>
        <!-- armrests -->
        <rect x="60"  y="140" width="28" height="9" rx="4" fill="#5a2f9e"/>
        <rect x="254" y="140" width="28" height="9" rx="4" fill="#5a2f9e"/>
      </g>

      <!-- ─── GUY (left) ──────────────────────── -->
      <g class="char-group char-guy">
        <!-- body -->
        <rect x="92" y="98" width="46" height="52" rx="14" fill="#3b82f6"/>
        <rect x="98" y="103" width="32" height="22" rx="8" fill="#60a5fa"/>
        <!-- collar -->
        <polygon points="115,98 125,98 120,108" fill="#1d4ed8"/>
        <!-- pants -->
        <rect x="92"  y="142" width="20" height="20" rx="6" fill="#1e3a5f"/>
        <rect x="118" y="142" width="20" height="20" rx="6" fill="#1e3a5f"/>
        <!-- shoes -->
        <ellipse cx="102" cy="163" rx="11" ry="6" fill="#111"/>
        <ellipse cx="128" cy="163" rx="11" ry="6" fill="#111"/>
        <!-- head -->
        <circle cx="115" cy="82" r="22" fill="#f5c8a0"/>
        <!-- hair -->
        <ellipse cx="115" cy="63" rx="19" ry="10" fill="#3b1f0a"/>
        <rect x="96" y="60" width="38" height="14" rx="7" fill="#3b1f0a"/>
        <!-- ear -->
        <circle cx="93"  cy="82" r="5" fill="#e8b48a"/>
        <circle cx="137" cy="82" r="5" fill="#e8b48a"/>
        <!-- eyes – happy -->
        <path d="M107 80 Q110 76 113 80" stroke="#333" stroke-width="2.2" stroke-linecap="round" fill="none"/>
        <path d="M117 80 Q120 76 123 80" stroke="#333" stroke-width="2.2" stroke-linecap="round" fill="none"/>
        <!-- smile -->
        <path d="M108 89 Q115 96 122 89" stroke="#c0725a" stroke-width="2" stroke-linecap="round" fill="none"/>
        <!-- blush -->
        <ellipse class="blush" cx="103" cy="89" rx="7" ry="4" fill="#ff8fa3" opacity=".55"/>
        <ellipse class="blush" cx="127" cy="89" rx="7" ry="4" fill="#ff8fa3" opacity=".55"/>
        <!-- sad eyes (inactive) – hidden by default via clip / opacity trick -->
        <ellipse class="tear" cx="106" cy="91" rx="2.5" ry="3.5" fill="#60a5fa" opacity="0.8"/>
        <ellipse class="tear" cx="124" cy="91" rx="2.5" ry="3.5" fill="#60a5fa" opacity="0.8"/>

        <!-- ARM + FLOWER ────────────────────── -->
        <g class="flower-stem">
          <!-- arm reaching toward girl -->
          <path d="M136 118 Q158 105 168 108" stroke="#f5c8a0" stroke-width="10" stroke-linecap="round" fill="none"/>
          <!-- stem -->
          <line x1="168" y1="108" x2="173" y2="88" stroke="#22c55e" stroke-width="3" stroke-linecap="round"/>
          <!-- leaf -->
          <ellipse cx="171" cy="98" rx="6" ry="3" fill="#16a34a" transform="rotate(-30 171 98)"/>
          <!-- flower head -->
          <circle cx="173" cy="83" r="8" fill="#fbbf24"/>
          <circle cx="173" cy="75" r="5" fill="#f472b6"/>
          <circle cx="173" cy="91" r="5" fill="#f472b6"/>
          <circle cx="165" cy="83" r="5" fill="#f472b6"/>
          <circle cx="181" cy="83" r="5" fill="#f472b6"/>
          <circle cx="167" cy="77" r="4.5" fill="#f472b6"/>
          <circle cx="179" cy="77" r="4.5" fill="#f472b6"/>
          <circle cx="167" cy="89" r="4.5" fill="#f472b6"/>
          <circle cx="179" cy="89" r="4.5" fill="#f472b6"/>
          <circle cx="173" cy="83" r="6" fill="#fde047"/>
        </g>
      </g>

      <!-- ─── GIRL (right) ────────────────────── -->
      <g class="char-group char-girl">
        <!-- dress -->
        <path d="M198 100 Q195 148 192 162 L228 162 Q225 148 222 100 Z" fill="#f472b6"/>
        <path d="M198 100 Q210 106 222 100 L228 162 L192 162 Z" fill="#fb7ab5"/>
        <!-- sleeve left -->
        <path d="M198 108 Q183 118 180 128" stroke="#f472b6" stroke-width="14" stroke-linecap="round" fill="none"/>
        <!-- sleeve right -->
        <path d="M222 108 Q237 118 240 128" stroke="#f472b6" stroke-width="14" stroke-linecap="round" fill="none"/>
        <!-- hand receiving flower (open palm gesture) -->
        <ellipse cx="182" cy="128" rx="8" ry="6" fill="#f5c8a0"/>
        <!-- shoes -->
        <ellipse cx="200" cy="164" rx="10" ry="6" fill="#db2777"/>
        <ellipse cx="220" cy="164" rx="10" ry="6" fill="#db2777"/>
        <!-- head -->
        <circle cx="210" cy="78" r="24" fill="#f5c8a0"/>
        <!-- hair – long -->
        <ellipse cx="210" cy="56" rx="21" ry="11" fill="#3b1f0a"/>
        <rect x="189" y="55" width="42" height="18" rx="9" fill="#3b1f0a"/>
        <path d="M189 68 Q183 100 186 140" stroke="#3b1f0a" stroke-width="14" stroke-linecap="round" fill="none"/>
        <path d="M231 68 Q237 100 234 140" stroke="#3b1f0a" stroke-width="14" stroke-linecap="round" fill="none"/>
        <!-- hair highlight -->
        <path d="M195 58 Q204 52 215 56" stroke="#6b3f1a" stroke-width="3" stroke-linecap="round" fill="none" opacity=".6"/>
        <!-- ears -->
        <circle cx="186" cy="79" r="5" fill="#e8b48a"/>
        <circle cx="234" cy="79" r="5" fill="#e8b48a"/>
        <!-- earring -->
        <circle cx="234" cy="85" r="3" fill="#f472b6"/>
        <!-- eyes – happy curve -->
        <path d="M200 76 Q204 72 208 76" stroke="#333" stroke-width="2.2" stroke-linecap="round" fill="none"/>
        <path d="M212 76 Q216 72 220 76" stroke="#333" stroke-width="2.2" stroke-linecap="round" fill="none"/>
        <!-- lashes -->
        <line x1="200" y1="76" x2="198" y2="73" stroke="#333" stroke-width="1.5"/>
        <line x1="220" y1="76" x2="222" y2="73" stroke="#333" stroke-width="1.5"/>
        <!-- smile -->
        <path d="M203 86 Q210 94 217 86" stroke="#c0725a" stroke-width="2" stroke-linecap="round" fill="none"/>
        <!-- blush -->
        <ellipse class="blush" cx="198" cy="87" rx="7" ry="4" fill="#ff8fa3" opacity=".55"/>
        <ellipse class="blush" cx="222" cy="87" rx="7" ry="4" fill="#ff8fa3" opacity=".55"/>
        <!-- sad tears (inactive) -->
        <ellipse class="tear" cx="202" cy="88" rx="2.5" ry="3.5" fill="#60a5fa" opacity="0.8"/>
        <ellipse class="tear" cx="218" cy="88" rx="2.5" ry="3.5" fill="#60a5fa" opacity="0.8"/>
        <!-- hair accessory -->
        <circle cx="226" cy="58" r="6" fill="#f472b6"/>
        <circle cx="226" cy="58" r="3" fill="#fde047"/>
      </g>

      <!-- ─── FLOATING HEARTS ─────────────────── -->
      <g>
        <text class="heart-float" x="160" y="58" font-size="14" text-anchor="middle">💗</text>
        <text class="heart-float" x="172" y="48" font-size="10" text-anchor="middle" style="animation-delay:1s">💕</text>
        <text class="heart-float" x="183" y="62" font-size="12" text-anchor="middle" style="animation-delay:2s">💖</text>
      </g>
    </svg>`

function CoupleIllustration() {
  return (
    <div className="couple-wrap">
      <div className="inactive-msg">💔 It's been 7 days… they miss each other!</div>
      <div dangerouslySetInnerHTML={{ __html: illustration }} />
    </div>
  )
}

export default memo(CoupleIllustration)
