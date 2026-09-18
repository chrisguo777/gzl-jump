Page({
  onLoad() {
    this.initCanvas()
  },

  onUnload() {
    if (this.rafId && this.canvas) {
      this.canvas.cancelAnimationFrame(this.rafId)
    }
  },

  // ─── Canvas init ───────────────────────────────────────────────────────────

  initCanvas() {
    wx.createSelectorQuery()
      .in(this)
      .select('#c')
      .fields({ node: true, size: true })
      .exec(res => {
        const canvas = res[0].node
        const ctx = canvas.getContext('2d')
        const sys = wx.getSystemInfoSync()

        this.dpr = sys.pixelRatio
        this.W = sys.windowWidth
        this.H = sys.windowHeight

        canvas.width = this.W * this.dpr
        canvas.height = this.H * this.dpr
        ctx.scale(this.dpr, this.dpr)

        this.canvas = canvas
        this.ctx = ctx

        const img = canvas.createImage()
        img.onload = () => { this.charImg = img; this.reset(); this.tick() }
        img.onerror = () => { this.charImg = null; this.reset(); this.tick() }
        img.src = '/images/gzl.png'
      })
  },

  // ─── Game state ────────────────────────────────────────────────────────────

  reset() {
    const H = this.H

    this.state = 'start'  // start | play | charge | dead
    this.score = 0
    this.best = wx.getStorageSync('gzl_best') || 0

    this.camX = 0

    // Physics
    this.G = 0.48

    // Floor level for first platform
    this.floorY = H * 0.63

    // Character  44 × 76 px
    const CW = 44, CH = 76
    this.ch = {
      x: 88, y: this.floorY - CH,
      w: CW, h: CH,
      vx: 0, vy: 0,
      ground: true,
      sqX: 1, sqY: 1   // squish scale during charge
    }

    // Charge state
    this.chargeT = 0       // 0-1
    this.chargeMs = 0      // Date.now() when charge started

    // Platforms
    this.plats = [{ x: 40, y: this.floorY, w: 125, h: 20 }]
    this.platIdx = 0
    for (let i = 0; i < 7; i++) this.addPlat()

    // Particles
    this.parts = []

    // Dead screen timer (frames)
    this.deadFrames = 0
  },

  addPlat() {
    const last = this.plats[this.plats.length - 1]
    const gap = 80 + Math.random() * 120          // 80-200 px
    const dy  = (Math.random() - 0.5) * 70        // ±35 px height shift
    const ny  = Math.max(this.H * 0.42, Math.min(this.H * 0.76, last.y + dy))
    const nw  = 65 + Math.random() * 65           // 65-130 px wide
    this.plats.push({ x: last.x + last.w + gap, y: ny, w: nw, h: 20 })
  },

  // ─── Touch ─────────────────────────────────────────────────────────────────

  onTouchStart() {
    const s = this.state
    if (s === 'start') { this.state = 'play'; return }
    if (s === 'dead' && this.deadFrames > 55) { this.reset(); return }
    if (s === 'play' && this.ch.ground) {
      this.state = 'charge'
      this.chargeMs = Date.now()
      this.chargeT = 0
    }
  },

  onTouchEnd() {
    if (this.state === 'charge') this.doJump()
  },

  doJump() {
    const t = this.chargeT
    this.ch.vx = 3 + 4.5 * t    // 3 – 7.5
    this.ch.vy = -(7 + 4 * t)   // -7 – -11
    this.ch.ground = false
    this.ch.sqX = 1; this.ch.sqY = 1
    this.state = 'play'
    this.chargeT = 0
  },

  // ─── Update ────────────────────────────────────────────────────────────────

  update() {
    if (this.state === 'dead') {
      this.deadFrames++
      this.updateParts()
      return
    }
    if (this.state === 'start') return

    if (this.state === 'charge') {
      this.chargeT = Math.min(1, (Date.now() - this.chargeMs) / 1800)
      this.ch.sqX = 1 + this.chargeT * 0.2
      this.ch.sqY = 1 - this.chargeT * 0.28
      return
    }

    // Physics
    this.ch.vy += this.G
    this.ch.x  += this.ch.vx
    this.ch.y  += this.ch.vy

    this.checkCollision()

    if (this.ch.y > this.H + 120) {
      this.die()
      return
    }

    // Smooth camera follow
    const target = this.ch.x - this.W * 0.33
    this.camX += (target - this.camX) * 0.11

    // Spawn platforms ahead
    const last = this.plats[this.plats.length - 1]
    if (last.x - this.camX < this.W + 250) this.addPlat()

    this.updateParts()
  },

  checkCollision() {
    const ch = this.ch
    ch.ground = false

    const start = Math.max(0, this.platIdx - 1)
    const end   = Math.min(this.plats.length, this.platIdx + 5)

    for (let i = start; i < end; i++) {
      const p = this.plats[i]
      const bot  = ch.y + ch.h
      const left = ch.x + 7
      const rgt  = ch.x + ch.w - 7

      if (ch.vy >= 0 &&
          bot >= p.y &&
          bot <= p.y + p.h + Math.abs(ch.vy) + 2 &&
          rgt > p.x &&
          left < p.x + p.w) {

        ch.y = p.y - ch.h
        ch.vy = 0
        ch.vx = 0
        ch.ground = true

        if (i > this.platIdx) {
          this.score += i - this.platIdx
          this.platIdx = i
          this.spawnLandParts(ch.x + ch.w / 2, ch.y + ch.h)
        }
        break
      }
    }
  },

  // ─── Particles ─────────────────────────────────────────────────────────────

  spawnLandParts(x, y) {
    for (let i = 0; i < 10; i++) {
      const ang = Math.PI * (0.1 + Math.random() * 0.8)  // upward arc
      const spd = 2 + Math.random() * 4
      this.parts.push({
        x, y,
        vx: Math.cos(ang) * spd * (Math.random() > 0.5 ? 1 : -1),
        vy: -Math.abs(Math.sin(ang)) * spd,
        life: 1,
        r: 2 + Math.random() * 2,
        hue: 110 + Math.random() * 60
      })
    }
  },

  spawnDeathParts() {
    const ch = this.ch
    for (let i = 0; i < 22; i++) {
      const ang = Math.random() * Math.PI * 2
      const spd = 2 + Math.random() * 7
      this.parts.push({
        x: ch.x + ch.w / 2, y: ch.y + ch.h / 2,
        vx: Math.cos(ang) * spd,
        vy: Math.sin(ang) * spd - 3,
        life: 1,
        r: 2 + Math.random() * 3,
        hue: Math.random() * 60
      })
    }
  },

  updateParts() {
    this.parts = this.parts.filter(p => {
      p.x += p.vx; p.y += p.vy
      p.vy += 0.18
      p.life -= 0.033
      return p.life > 0
    })
  },

  die() {
    this.state = 'dead'
    this.deadFrames = 0
    if (this.score > this.best) {
      this.best = this.score
      wx.setStorageSync('gzl_best', this.best)
    }
    this.spawnDeathParts()
  },

  // ─── Draw ──────────────────────────────────────────────────────────────────

  draw() {
    const ctx = this.ctx
    const W = this.W, H = this.H

    ctx.clearRect(0, 0, W, H)
    this.drawBg()

    ctx.save()
    ctx.translate(-Math.floor(this.camX), 0)
    this.drawPlats()
    this.drawParts()
    this.drawChar()
    ctx.restore()

    this.drawUI()
  },

  drawBg() {
    const ctx = this.ctx
    const W = this.W, H = this.H

    // Dark gradient backdrop
    const bg = ctx.createLinearGradient(0, 0, 0, H)
    bg.addColorStop(0, '#060a0f')
    bg.addColorStop(0.55, '#0c1520')
    bg.addColorStop(1, '#080e18')
    ctx.fillStyle = bg
    ctx.fillRect(0, 0, W, H)

    // ── Far parallax: ceiling fluorescent strips ──
    const litOff = (this.camX * 0.15) % 240
    for (let x = -(litOff % 240); x < W + 240; x += 240) {
      // Diffuse glow column
      const glow = ctx.createLinearGradient(x + 5, 0, x + 85, 0)
      glow.addColorStop(0,   'rgba(140,230,155,0)')
      glow.addColorStop(0.3, 'rgba(140,230,155,0.055)')
      glow.addColorStop(0.7, 'rgba(140,230,155,0.055)')
      glow.addColorStop(1,   'rgba(140,230,155,0)')
      ctx.fillStyle = glow
      ctx.fillRect(x, 0, 90, H)

      // Tube itself
      ctx.fillStyle = 'rgba(190,255,200,0.18)'
      ctx.fillRect(x + 10, 8, 70, 4)
    }

    // ── Mid parallax: concrete wall panels ──
    const wallOff = (this.camX * 0.32) % 280
    ctx.strokeStyle = 'rgba(55, 85, 65, 0.28)'
    ctx.lineWidth = 1
    for (let x = -(wallOff % 280); x < W + 280; x += 280) {
      ctx.strokeRect(x + 8,   48, 135, H * 0.46)
      ctx.strokeRect(x + 155, 62, 105, H * 0.36)
    }

    // ── Near parallax: DANGER signs ──
    const dOff = (this.camX * 0.45) % 520
    const dx = -(dOff % 520) + 30
    ctx.fillStyle = 'rgba(190, 45, 45, 0.3)'
    ctx.fillRect(dx, 66, 42, 20)
    ctx.fillStyle = 'rgba(255, 110, 110, 0.5)'
    ctx.font = '6px Arial'
    ctx.textAlign = 'center'
    ctx.fillText('DANGER', dx + 21, 74)
    ctx.fillText('HIGH VOLTAGE', dx + 21, 82)
    ctx.textAlign = 'left'
  },

  drawPlats() {
    const ctx = this.ctx
    const H = this.H
    const camX = this.camX, W = this.W

    for (let i = 0; i < this.plats.length; i++) {
      const p = this.plats[i]
      if (p.x + p.w < camX - 60 || p.x > camX + W + 60) continue

      const isCur  = i === this.platIdx
      const isNext = i === this.platIdx + 1

      // Glow hint on next platform
      if (isNext) {
        ctx.shadowColor = 'rgba(80, 230, 110, 0.45)'
        ctx.shadowBlur  = 14
      }

      // Body gradient
      const grad = ctx.createLinearGradient(p.x, p.y, p.x, p.y + p.h)
      if (isCur) {
        grad.addColorStop(0, '#3d6b4c')
        grad.addColorStop(1, '#1d3624')
      } else if (isNext) {
        grad.addColorStop(0, '#4c7c5a')
        grad.addColorStop(1, '#25412e')
      } else {
        grad.addColorStop(0, '#2a4e37')
        grad.addColorStop(1, '#14261b')
      }
      ctx.fillStyle = grad
      ctx.fillRect(p.x, p.y, p.w, p.h)

      // Metal grate lines
      ctx.strokeStyle = 'rgba(95, 170, 115, 0.22)'
      ctx.lineWidth = 0.5
      for (let gx = p.x + 11; gx < p.x + p.w - 4; gx += 11) {
        ctx.beginPath()
        ctx.moveTo(gx, p.y)
        ctx.lineTo(gx, p.y + p.h)
        ctx.stroke()
      }

      // Top edge highlight
      const hlAlpha = isNext ? 0.55 : 0.35
      ctx.fillStyle = `rgba(100, 240, 130, ${hlAlpha})`
      ctx.fillRect(p.x, p.y, p.w, 2)

      // Support pillars going down
      ctx.fillStyle = '#101a12'
      ctx.fillRect(p.x + 5,           p.y + p.h, 7, H - p.y)
      ctx.fillRect(p.x + p.w - 12,    p.y + p.h, 7, H - p.y)

      ctx.shadowBlur = 0
    }
  },

  drawChar() {
    const ctx = this.ctx
    const ch = this.ch

    // Ground shadow
    if (ch.ground) {
      ctx.fillStyle = 'rgba(0,0,0,0.28)'
      ctx.beginPath()
      ctx.ellipse(ch.x + ch.w / 2, ch.y + ch.h + 1, ch.w * 0.38, 4, 0, 0, Math.PI * 2)
      ctx.fill()
    }

    const cx = ch.x + ch.w / 2
    const cy = ch.y + ch.h / 2

    ctx.save()
    ctx.translate(cx, cy)
    ctx.scale(ch.sqX, ch.sqY)

    // Soft green aura (Source Engine vibe)
    ctx.shadowColor = 'rgba(160, 255, 180, 0.22)'
    ctx.shadowBlur  = 12

    if (this.charImg) {
      ctx.drawImage(this.charImg, -ch.w / 2, -ch.h / 2, ch.w, ch.h)
    } else {
      // Placeholder silhouette
      ctx.fillStyle = '#bb88aa'
      ctx.fillRect(-ch.w / 2, -ch.h / 2, ch.w, ch.h)
    }

    ctx.shadowBlur = 0
    ctx.restore()

    // Charge power bar
    if (this.state === 'charge') {
      const bw = 50, bh = 5
      const bx = ch.x + ch.w / 2 - bw / 2
      const by = ch.y - 18

      ctx.fillStyle = 'rgba(0,0,0,0.55)'
      ctx.fillRect(bx - 1, by - 1, bw + 2, bh + 2)

      const barGrad = ctx.createLinearGradient(bx, 0, bx + bw, 0)
      barGrad.addColorStop(0,    '#44ee66')
      barGrad.addColorStop(0.65, '#eedd22')
      barGrad.addColorStop(1,    '#ee4422')
      ctx.fillStyle = barGrad
      ctx.fillRect(bx, by, bw * this.chargeT, bh)

      ctx.strokeStyle = 'rgba(255,255,255,0.28)'
      ctx.lineWidth = 1
      ctx.strokeRect(bx - 1, by - 1, bw + 2, bh + 2)
    }
  },

  drawParts() {
    const ctx = this.ctx
    for (const p of this.parts) {
      ctx.globalAlpha = p.life
      ctx.fillStyle   = `hsl(${p.hue}, 80%, 65%)`
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fill()
    }
    ctx.globalAlpha = 1
  },

  drawUI() {
    const ctx = this.ctx
    const W = this.W, H = this.H

    // ── Start screen ────────────────────────────────────────────────────────
    if (this.state === 'start') {
      ctx.fillStyle = 'rgba(0,0,0,0.58)'
      ctx.fillRect(0, 0, W, H)

      ctx.textAlign = 'center'

      // Title with glow
      ctx.shadowColor = 'rgba(100,255,130,0.65)'
      ctx.shadowBlur  = 22
      ctx.fillStyle   = '#88ffaa'
      ctx.font        = 'bold 40px Arial'
      ctx.fillText('GZL 闯关', W / 2, H * 0.33)
      ctx.shadowBlur  = 0

      ctx.fillStyle = 'rgba(205,240,215,0.78)'
      ctx.font      = '17px Arial'
      ctx.fillText('长按蓄力  松手起跳', W / 2, H * 0.44)

      if (this.best > 0) {
        ctx.fillStyle = 'rgba(180,225,195,0.55)'
        ctx.font      = '14px Arial'
        ctx.fillText('最高 ' + this.best + ' 分', W / 2, H * 0.51)
      }

      // Pulsing tap prompt
      const pulse = 0.55 + 0.45 * Math.sin(Date.now() / 520)
      ctx.globalAlpha = pulse
      ctx.fillStyle   = '#88ffaa'
      ctx.font        = '19px Arial'
      ctx.fillText('点击开始', W / 2, H * 0.63)
      ctx.globalAlpha = 1

      ctx.textAlign = 'left'
      return
    }

    // ── Game over screen ─────────────────────────────────────────────────────
    if (this.state === 'dead') {
      ctx.fillStyle = 'rgba(0,0,0,0.62)'
      ctx.fillRect(0, 0, W, H)

      ctx.textAlign = 'center'

      ctx.fillStyle = '#ff7777'
      ctx.font      = 'bold 30px Arial'
      ctx.fillText('游戏结束', W / 2, H * 0.37)

      ctx.shadowColor = 'rgba(255,255,100,0.5)'
      ctx.shadowBlur  = 16
      ctx.fillStyle   = '#ffffff'
      ctx.font        = 'bold 56px Arial'
      ctx.fillText(this.score, W / 2, H * 0.51)
      ctx.shadowBlur  = 0

      if (this.score > 0 && this.score >= this.best) {
        ctx.fillStyle = '#ffdd44'
        ctx.font      = 'bold 17px Arial'
        ctx.fillText('新纪录！', W / 2, H * 0.59)
      } else {
        ctx.fillStyle = 'rgba(200,225,205,0.6)'
        ctx.font      = '15px Arial'
        ctx.fillText('最高 ' + this.best + ' 分', W / 2, H * 0.59)
      }

      if (this.deadFrames > 55) {
        const pulse2 = 0.55 + 0.45 * Math.sin(Date.now() / 450)
        ctx.globalAlpha = pulse2
        ctx.fillStyle   = '#88ffaa'
        ctx.font        = '18px Arial'
        ctx.fillText('点击重新开始', W / 2, H * 0.73)
        ctx.globalAlpha = 1
      }

      ctx.textAlign = 'left'
      return
    }

    // ── In-game score (top-right) ────────────────────────────────────────────
    ctx.fillStyle = 'rgba(0,0,0,0.38)'
    ctx.fillRect(W - 98, 14, 83, 40)

    ctx.fillStyle = 'rgba(185,230,200,0.5)'
    ctx.font      = '11px Arial'
    ctx.textAlign = 'right'
    ctx.fillText('分数', W - 18, 26)

    ctx.fillStyle = '#77ffaa'
    ctx.font      = 'bold 24px Arial'
    ctx.fillText(this.score, W - 18, 46)
    ctx.textAlign = 'left'
  },

  // ─── Loop ──────────────────────────────────────────────────────────────────

  tick() {
    this.update()
    this.draw()
    this.rafId = this.canvas.requestAnimationFrame(this.tick.bind(this))
  }
})
