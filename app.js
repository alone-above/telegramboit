/* ═══════════════════════════════════════════
   Alone Above Shop — Telegram Mini App
   app.js
═══════════════════════════════════════════ */

// ─── State ───────────────────────────────────────────
const State = {
  config: null,
  tg: null,
  user: null,
  cart: [],
  favorites: [],
  products: [],
  categories: [],
  orders: [],
  currentPage: 'home',
  currentCategory: null,
  searchQuery: '',
  currentProduct: null,
  currentImgIndex: 0,
  apiBase: '',
};

// ─── Telegram WebApp Init ─────────────────────────────
function initTelegram() {
  const tg = window.Telegram?.WebApp;
  if (!tg) { console.warn('Not in Telegram'); return null; }
  tg.ready();
  tg.expand();
  tg.disableVerticalSwipes?.();
  tg.setHeaderColor?.('#0d0d0d');
  tg.setBackgroundColor?.('#0d0d0d');
  return tg;
}

// ─── Local Storage helpers ────────────────────────────
function lsGet(key, def = null) {
  try { const v = localStorage.getItem(key); return v !== null ? JSON.parse(v) : def; } catch { return def; }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}

// ─── Toast ────────────────────────────────────────────
function toast(msg, type = 'info', dur = 2500) {
  const icons = { success: '✅', error: '❌', info: 'ℹ️', cart: '🛒' };
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${msg}</span>`;
  const cont = document.getElementById('toast-container');
  if (!cont) return;
  cont.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(-8px)'; el.style.transition = 'all 0.3s'; setTimeout(() => el.remove(), 300); }, dur);
}

// ─── API ──────────────────────────────────────────────
async function api(path, opts = {}) {
  try {
    const userId = State.user?.id;
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (userId) headers['X-User-Id'] = userId;
    const res = await fetch(State.apiBase + path, { ...opts, headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error('API error:', e);
    return null;
  }
}

async function apiPost(path, body) {
  return api(path, { method: 'POST', body: JSON.stringify(body) });
}

// ─── Cart (local + server sync) ───────────────────────
function cartLoad() {
  State.cart = lsGet('cart_v2', []);
  updateCartBadge();
}
function cartSave() { lsSet('cart_v2', State.cart); }

function cartAdd(product, size) {
  const existing = State.cart.find(i => i.product_id == product.id && i.size === size);
  if (existing) { toast('Уже в корзине', 'info'); return; }
  State.cart.push({
    product_id: product.id,
    name: product.name,
    price: product.price,
    size,
    card_file_id: product.card_file_id || '',
    card_media_type: product.card_media_type || '',
  });
  cartSave();
  updateCartBadge();
  toast('Добавлено в корзину', 'cart');
  State.tg?.HapticFeedback?.impactOccurred?.('light');
}

function cartRemove(productId, size) {
  State.cart = State.cart.filter(i => !(i.product_id == productId && i.size === size));
  cartSave();
  updateCartBadge();
  renderCart();
}

function cartClear() { State.cart = []; cartSave(); updateCartBadge(); renderCart(); }

function updateCartBadge() {
  const n = State.cart.length;
  ['cart-badge-nav', 'cart-badge-header'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = n; el.style.display = n ? 'flex' : 'none'; }
  });
}

// ─── Favorites (local) ────────────────────────────────
function favsLoad() { State.favorites = lsGet('favorites_v2', []); }
function favsSave() { lsSet('favorites_v2', State.favorites); }

function favToggle(productId) {
  const idx = State.favorites.indexOf(productId);
  if (idx >= 0) { State.favorites.splice(idx, 1); toast('Удалено из избранного', 'info'); }
  else { State.favorites.push(productId); toast('Добавлено в избранное', 'success'); }
  favsSave();
  updateFavBadge();
  return idx < 0;
}
function isFav(productId) { return State.favorites.includes(productId); }
function updateFavBadge() {
  const el = document.getElementById('fav-badge-nav');
  const n = State.favorites.length;
  if (el) { el.textContent = n; el.style.display = n ? 'flex' : 'none'; }
}

// ─── Navigation ───────────────────────────────────────
function navigate(page) {
  if (State.currentPage === page) return;
  State.currentPage = page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');
  const navEl = document.querySelector(`[data-nav="${page}"]`);
  if (navEl) navEl.classList.add('active');

  if (page === 'home') renderHome();
  if (page === 'catalog') renderCatalog();
  if (page === 'cart') renderCart();
  if (page === 'favorites') renderFavorites();
  if (page === 'profile') renderProfile();
  if (page === 'drops') renderDrops();
  if (page === 'support') renderSupport();
  if (page === 'about') renderAbout();
  if (page === 'bonuses') renderBonuses();
  if (page === 'orders') renderOrders();

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─── Product image helper ─────────────────────────────
function productImg(p, cls = '') {
  if (p.card_file_id) {
    // Telegram file_id — need to use a proxy or show placeholder
    return `<div class="product-card__img-placeholder ${cls}">🛍️</div>`;
  }
  // Attempt direct URL in description or fallback
  return `<div class="product-card__img-placeholder ${cls}">🛍️</div>`;
}

// ─── Format price ─────────────────────────────────────
function fmtPrice(p) {
  if (!p && p !== 0) return '—';
  return Number(p).toLocaleString('ru-RU') + ' ₸';
}

// ─── Format date ─────────────────────────────────────
function fmtDate(s) {
  if (!s) return '—';
  try { return new Date(s).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }); }
  catch { return s; }
}

// ─── Render Home ──────────────────────────────────────
function renderHome() {
  const cfg = State.config;
  if (!cfg) return;

  // Hero
  const hero = document.getElementById('hero-section');
  if (hero) {
    hero.style.backgroundImage = `url("${cfg.hero.bg_image}")`;
  }

  // Featured products
  const featuredEl = document.getElementById('home-featured');
  if (featuredEl) {
    const featured = State.products.slice(0, 4);
    if (featured.length) {
      featuredEl.innerHTML = featured.map((p, i) => productCardHTML(p, `delay-${i+1}`)).join('');
    } else {
      featuredEl.innerHTML = skeletonGrid(4);
    }
  }

  // New arrivals
  const newEl = document.getElementById('home-new');
  if (newEl) {
    const newArr = State.products.slice(4, 8);
    if (newArr.length) {
      newEl.innerHTML = newArr.map((p, i) => productCardHTML(p, `delay-${i+1}`)).join('');
    } else {
      newEl.innerHTML = State.products.length === 0 ? skeletonGrid(4) : '';
    }
  }

  // Update sale banner
  const banner = document.getElementById('sale-banner-img');
  if (banner && cfg.sale_banner?.bg_image) {
    banner.style.backgroundImage = `url("${cfg.sale_banner.bg_image}")`;
  }
}

function skeletonGrid(n) {
  return Array(n).fill('').map(() => `
    <div class="product-card">
      <div class="skeleton" style="height:160px"></div>
      <div class="product-card__body">
        <div class="skeleton" style="height:12px;margin-bottom:8px"></div>
        <div class="skeleton" style="height:16px;width:60%"></div>
      </div>
    </div>`).join('');
}

function productCardHTML(p, animClass = '') {
  const hasDiscount = p.original_price && p.original_price > p.price;
  const discPct = hasDiscount ? Math.round((1 - p.price / p.original_price) * 100) : 0;
  const favActive = isFav(p.id) ? 'active' : '';
  const favFill = isFav(p.id) ? 'fill="#ff6b6b" stroke="#ff6b6b"' : 'stroke="currentColor" fill="none"';
  const inStock = p.stock > 0;

  return `<div class="product-card animate-fade ${animClass}" onclick="openProduct(${p.id})">
    ${hasDiscount ? `<div class="product-card__badge">-${discPct}%</div>` : ''}
    <button class="product-card__wish ${favActive}" onclick="event.stopPropagation();wishToggle(${p.id},this)" aria-label="Избранное">
      <svg viewBox="0 0 24 24" ${favFill} stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
    </button>
    <div class="product-card__img-placeholder">🛍️</div>
    ${!inStock ? `<div class="product-card__no-stock"><span>Нет в наличии</span></div>` : ''}
    <div class="product-card__body">
      <div class="product-card__name">${p.name}</div>
      <div style="display:flex;align-items:center;flex-wrap:wrap">
        <span class="product-card__price">${fmtPrice(p.price)}</span>
        ${hasDiscount ? `<span class="product-card__original">${fmtPrice(p.original_price)}</span>` : ''}
      </div>
    </div>
  </div>`;
}

function wishToggle(pid, btn) {
  const isNow = favToggle(pid);
  if (btn) {
    btn.classList.toggle('active', isNow);
    btn.innerHTML = isNow
      ? `<svg viewBox="0 0 24 24" fill="#ff6b6b" stroke="#ff6b6b" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`;
  }
  State.tg?.HapticFeedback?.impactOccurred?.('light');
}

// ─── Render Catalog ───────────────────────────────────
function renderCatalog() {
  renderCatChips();
  renderProductGrid();
}

function renderCatChips() {
  const el = document.getElementById('cat-chips');
  if (!el) return;
  const cats = [{ id: null, name: '🔥 Все' }, ...State.categories.map(c => ({ id: c.id, name: c.name }))];
  el.innerHTML = cats.map(c => `
    <div class="cat-chip ${State.currentCategory == c.id ? 'active' : ''}" onclick="selectCat(${c.id})">
      ${c.name}
    </div>`).join('');
}

function selectCat(id) {
  State.currentCategory = id;
  renderCatChips();
  renderProductGrid();
}

function renderProductGrid() {
  const el = document.getElementById('product-grid');
  if (!el) return;
  let prods = State.products;
  if (State.currentCategory) prods = prods.filter(p => p.category_id == State.currentCategory);
  if (State.searchQuery) {
    const q = State.searchQuery.toLowerCase();
    prods = prods.filter(p => p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q));
  }
  if (!prods.length) {
    el.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="empty-state__icon">🔍</div>
      <div class="empty-state__title">Ничего не найдено</div>
      <div class="empty-state__desc">Попробуйте изменить фильтры</div>
    </div>`;
    return;
  }
  el.innerHTML = prods.map((p, i) => productCardHTML(p, `delay-${(i % 4) + 1}`)).join('');
}

// ─── Open Product ─────────────────────────────────────
function openProduct(pid) {
  // Implemented below as window.openProduct (after gallery JS loads)
  _openProductCore(pid);
}

function _openProductCore(pid) {
  const p = State.products.find(x => x.id == pid);
  if (!p) return;
  State.currentProduct = p;
  State.currentImgIndex = 0;
  renderProductDetail(p);
  const detail = document.getElementById('product-detail');
  detail.classList.add('open');
  State.tg?.BackButton?.show?.();
  State.tg?.BackButton?.onClick?.(() => closeProduct());
  document.body.style.overflow = 'hidden';
  requestAnimationFrame(() => initGalleryTouch());
}

function closeProduct() {
  document.getElementById('product-detail').classList.remove('open');
  State.tg?.BackButton?.hide?.();
  document.body.style.overflow = '';
}

function renderProductDetail(p) {
  const sizes = parseSizes(p.sizes);
  const hasDiscount = p.original_price && p.original_price > p.price;
  const discPct = hasDiscount ? Math.round((1 - p.price / p.original_price) * 100) : 0;

  // Build gallery array: card first, then gallery items
  const galleryItems = [];
  if (p.card_file_id) galleryItems.push({ file_id: p.card_file_id, media_type: p.card_media_type || 'photo' });
  const rawGallery = parseSizes(p.gallery); // reuse JSON parser
  rawGallery.forEach(g => {
    if (typeof g === 'string' && g) galleryItems.push({ file_id: g, media_type: 'photo' });
    else if (g && g.file_id) galleryItems.push(g);
  });
  State._galleryItems = galleryItems;
  State._galleryIdx = 0;

  // Seller info
  const isOfficial = !p.seller_username && !p.seller_phone;
  const sellerName = isOfficial ? (State.config?.shop?.name || 'Официальный магазин') : (p.seller_username ? '@' + p.seller_username : p.seller_phone || 'Продавец');
  // Seller avatar: custom file_id, official logo, or placeholder
  let sellerAvatarHTML;
  if (p.seller_avatar) {
    sellerAvatarHTML = `<div class="seller-avatar-placeholder" style="background:rgba(120,231,0,0.15)">👤</div>`;
    // We'll try to set real avatar via bot file proxy after render
  } else if (isOfficial) {
    sellerAvatarHTML = `<img src="${State.config?.shop?.logo || 'assets/logo.svg'}" alt="logo" class="seller-avatar">`;
  } else {
    sellerAvatarHTML = `<div class="seller-avatar-placeholder">👤</div>`;
  }

  const deliveryDays = p.delivery_days || '3–7';
  const warrantyDays = p.warranty_days || 14;
  const returnDays = p.return_days || 14;
  const discount = p.discount_percent ? `${p.discount_percent}%` : (hasDiscount ? `${discPct}%` : 'Нет');

  const el = document.getElementById('product-detail');
  el.innerHTML = `
    <div class="product-detail__back">
      <button class="btn btn-ghost btn-icon" onclick="closeProduct()">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
      </button>
      <span style="font-weight:600;font-size:16px">Товар</span>
      <button class="btn btn-ghost btn-icon" style="margin-left:auto" onclick="wishToggle(${p.id},this)" id="detail-wish-btn">
        <svg viewBox="0 0 24 24" ${isFav(p.id) ? 'fill="#ff6b6b" stroke="#ff6b6b"' : 'fill="none" stroke="currentColor"'} stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
      </button>
    </div>
    <div class="product-detail__imgs" id="detail-gallery-wrap">
      ${galleryItems.length > 0 ? `
        <div class="gallery-slider" id="gallery-slider" style="overflow:hidden;position:relative;background:var(--bg3);touch-action:pan-y">
          <div class="gallery-track" id="gallery-track" style="display:flex;transition:transform 0.35s cubic-bezier(0.4,0,0.2,1);width:${galleryItems.length * 100}%">
            ${galleryItems.map((g, i) => `
              <div style="width:${100 / galleryItems.length}%;flex-shrink:0;aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;background:var(--bg3)">
                <div class="gallery-slide-ph" data-idx="${i}" style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:80px">🛍️</div>
              </div>`).join('')}
          </div>
          ${galleryItems.length > 1 ? `
            <button onclick="galleryPrev()" style="position:absolute;left:8px;top:50%;transform:translateY(-50%);background:rgba(0,0,0,0.6);border:none;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;cursor:pointer;color:#fff;z-index:5">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M15 18l-6-6 6-6"/></svg>
            </button>
            <button onclick="galleryNext()" style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:rgba(0,0,0,0.6);border:none;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;cursor:pointer;color:#fff;z-index:5">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M9 18l6-6-6-6"/></svg>
            </button>
            <div style="position:absolute;bottom:10px;left:50%;transform:translateX(-50%);display:flex;gap:5px;z-index:5" id="gallery-dots">
              ${galleryItems.map((_, i) => `<div style="width:${i===0?'18px':'6px'};height:6px;border-radius:3px;background:${i===0?'var(--primary)':'rgba(255,255,255,0.4)'};transition:all 0.3s;cursor:pointer" onclick="galleryGoTo(${i})" id="gdot-${i}"></div>`).join('')}
            </div>
          ` : ''}
          <div style="position:absolute;top:10px;right:10px;background:rgba(0,0,0,0.6);padding:3px 8px;border-radius:10px;font-size:11px;color:#fff" id="gallery-counter">${galleryItems.length > 1 ? `1/${galleryItems.length}` : ''}</div>
        </div>
      ` : `<div class="product-detail__img-placeholder">🛍️</div>`}
    </div>
    <div class="product-detail__body">
      <div class="product-detail__meta">
        <span style="font-size:12px;color:var(--text2)">${p.category_name || ''}</span>
        ${p.stock > 0 ? `<span style="font-size:12px;color:var(--primary);font-weight:600">В наличии: ${p.stock} шт.</span>` : `<span style="font-size:12px;color:#ff6b6b;font-weight:600">Нет в наличии</span>`}
      </div>
      <div class="product-detail__name">${p.name}</div>
      <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:12px">
        <span class="product-detail__price">${fmtPrice(p.price)}</span>
        ${hasDiscount ? `<span class="product-detail__original">${fmtPrice(p.original_price)}</span>` : ''}
        ${hasDiscount ? `<span style="background:rgba(120,231,0,0.15);color:var(--primary);font-size:12px;font-weight:700;padding:2px 8px;border-radius:20px">-${discPct}%</span>` : ''}
      </div>
      <p class="product-detail__desc">${p.description || 'Описание отсутствует'}</p>

      <div class="product-detail__info-grid">
        <div class="info-chip">
          <div class="info-chip__icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12H19M19 12l-6-6m6 6-6 6"/></svg>
          </div>
          <div>
            <div class="info-chip__label">Доставка</div>
            <div class="info-chip__value">${deliveryDays} дней</div>
          </div>
        </div>
        <div class="info-chip">
          <div class="info-chip__icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </div>
          <div>
            <div class="info-chip__label">Гарантия</div>
            <div class="info-chip__value">${warrantyDays} дней</div>
          </div>
        </div>
        <div class="info-chip">
          <div class="info-chip__icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
          </div>
          <div>
            <div class="info-chip__label">Возврат</div>
            <div class="info-chip__value">${returnDays} дней</div>
          </div>
        </div>
        <div class="info-chip">
          <div class="info-chip__icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 12V22H4V12M22 7H2v5h20V7zM12 22V7M12 7H7.5a2.5 2.5 0 010-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 000-5C13 2 12 7 12 7z"/></svg>
          </div>
          <div>
            <div class="info-chip__label">Скидка</div>
            <div class="info-chip__value">${discount}</div>
          </div>
        </div>
      </div>

      ${sizes.length ? `
      <div class="sizes-section">
        <div class="sizes-label">Выберите размер</div>
        <div class="sizes-grid" id="sizes-grid">
          ${sizes.map((s, i) => `<button class="size-btn ${i === 0 ? 'active' : ''}" onclick="selectSize(this,'${s}')">${s}</button>`).join('')}
        </div>
      </div>` : ''}

      <div class="seller-card">
        ${sellerAvatarHTML}
        <div>
          <div style="font-size:12px;color:var(--text2);margin-bottom:2px">Продавец</div>
          <div style="font-size:14px;font-weight:600">${sellerName}</div>
          ${p.seller_phone ? `<div style="font-size:12px;color:var(--text2)">${p.seller_phone}</div>` : ''}
        </div>
      </div>
    </div>
    <div class="product-detail__actions">
      <button class="btn btn-outline btn-icon" onclick="wishToggle(${p.id},document.getElementById('detail-wish-btn'))" title="В избранное">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
      </button>
      ${p.stock > 0
        ? `<button class="btn btn-primary btn-full" onclick="addToCartFromDetail()">🛒 В корзину</button>`
        : `<button class="btn btn-full" style="background:var(--bg3);color:var(--text3)" disabled>Нет в наличии</button>`}
    </div>
  `;
}

function selectSize(btn, size) {
  document.querySelectorAll('#sizes-grid .size-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function addToCartFromDetail() {
  const p = State.currentProduct;
  if (!p) return;
  const activeSize = document.querySelector('#sizes-grid .size-btn.active');
  const size = activeSize ? activeSize.textContent.trim() : 'ONE SIZE';
  cartAdd(p, size);
  State.tg?.HapticFeedback?.notificationOccurred?.('success');
}

function parseSizes(sizes) {
  if (!sizes) return [];
  if (Array.isArray(sizes)) return sizes;
  try { return JSON.parse(sizes); } catch { return []; }
}

// ─── Render Cart ──────────────────────────────────────
function renderCart() {
  const el = document.getElementById('cart-list');
  const summaryEl = document.getElementById('cart-summary');
  const emptyEl = document.getElementById('cart-empty');
  const checkoutEl = document.getElementById('checkout-btn');
  if (!el) return;

  if (!State.cart.length) {
    el.innerHTML = '';
    if (summaryEl) summaryEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'block';
    if (checkoutEl) checkoutEl.style.display = 'none';
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';
  if (summaryEl) summaryEl.style.display = 'block';
  if (checkoutEl) checkoutEl.style.display = 'flex';

  el.innerHTML = State.cart.map((item, idx) => `
    <div class="cart-item animate-fade delay-${(idx % 4) + 1}">
      <div class="cart-item__img-ph">🛍️</div>
      <div class="cart-item__info">
        <div class="cart-item__name">${item.name}</div>
        <div class="cart-item__size">Размер: ${item.size}</div>
        <div class="cart-item__price">${fmtPrice(item.price)}</div>
      </div>
      <button class="cart-item__remove" onclick="cartRemove(${item.product_id},'${item.size}')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>`).join('');

  const total = State.cart.reduce((s, i) => s + i.price, 0);
  if (summaryEl) summaryEl.innerHTML = `
    <div class="cart-summary__row"><span>Товаров</span><span>${State.cart.length} шт.</span></div>
    <div class="cart-summary__row"><span style="font-size:16px">Итого</span><span class="cart-summary__total">${fmtPrice(total)}</span></div>
  `;
}

// ─── Checkout ─────────────────────────────────────────
function openCheckout() {
  if (!State.cart.length) { toast('Корзина пуста', 'error'); return; }
  const el = document.getElementById('checkout-modal');
  if (el) el.style.display = 'flex';
}
function closeCheckout() {
  const el = document.getElementById('checkout-modal');
  if (el) el.style.display = 'none';
}

async function submitOrder() {
  const phone = document.getElementById('checkout-phone')?.value?.trim();
  const address = document.getElementById('checkout-address')?.value?.trim();
  const promo = document.getElementById('checkout-promo')?.value?.trim();

  if (!phone) { toast('Введите номер телефона', 'error'); return; }
  if (!address) { toast('Введите адрес доставки', 'error'); return; }

  const btn = document.getElementById('submit-order-btn');
  if (btn) { btn.textContent = 'Оформляем...'; btn.disabled = true; }

  try {
    const res = await apiPost('/order/create', {
      user_id: State.user?.id,
      items: State.cart.map(i => ({ product_id: i.product_id, size: i.size })),
      phone, address,
      promo_code: promo || '',
      method: 'kaspi',
    });

    if (res?.success) {
      closeCheckout();
      cartClear();
      const oid = res.order_id;
      const amount = res.payment_info?.amount;
      const kaspiPhone = State.config?.contact?.kaspi_phone || res.payment_info?.phone;
      // Show payment info
      const successEl = document.getElementById('order-success-modal');
      if (successEl) {
        document.getElementById('success-order-id').textContent = `#${oid}`;
        document.getElementById('success-amount').textContent = fmtPrice(amount);
        document.getElementById('success-kaspi').textContent = kaspiPhone;
        successEl.style.display = 'flex';
      }
      State.tg?.HapticFeedback?.notificationOccurred?.('success');
    } else {
      toast(res?.error || 'Ошибка при оформлении', 'error');
    }
  } catch {
    toast('Ошибка соединения', 'error');
  } finally {
    if (btn) { btn.textContent = 'Оформить заказ'; btn.disabled = false; }
  }
}

// ─── Render Favorites ─────────────────────────────────
function renderFavorites() {
  const el = document.getElementById('fav-grid');
  if (!el) return;
  const favProds = State.products.filter(p => State.favorites.includes(p.id));
  if (!favProds.length) {
    el.innerHTML = `<div class="empty-state" style="grid-column:1/-1">
      <div class="empty-state__icon">❤️</div>
      <div class="empty-state__title">Избранное пусто</div>
      <div class="empty-state__desc">Добавляйте товары в избранное, нажимая на ❤️</div>
      <button class="btn btn-primary" onclick="navigate('catalog')">Перейти в каталог</button>
    </div>`;
    return;
  }
  el.innerHTML = favProds.map((p, i) => productCardHTML(p, `delay-${(i % 4) + 1}`)).join('');
}

// ─── Render Profile ───────────────────────────────────
function renderProfile() {
  const u = State.user;
  const profileCard = document.getElementById('profile-card');
  if (!profileCard) return;
  const name = u ? `${u.first_name || ''} ${u.last_name || ''}`.trim() || `User ${u.id}` : 'Гость';
  const username = u?.username ? `@${u.username}` : '';
  const photoUrl = u?.photo_url || null;

  document.getElementById('profile-name').textContent = name;
  document.getElementById('profile-username').textContent = username;
  if (photoUrl) {
    const img = document.getElementById('profile-avatar');
    if (img) { img.src = photoUrl; img.style.display = 'block'; }
    const ph = document.getElementById('profile-avatar-ph');
    if (ph) ph.style.display = 'none';
  }

  // Orders count
  document.getElementById('stat-orders').textContent = State.orders.length;
  // Bonuses
  document.getElementById('stat-bonus').textContent = '0';
  // Favorites
  document.getElementById('stat-favs').textContent = State.favorites.length;
}

// ─── Render Orders ────────────────────────────────────
async function renderOrders() {
  const el = document.getElementById('orders-list');
  if (!el) return;
  el.innerHTML = '<div class="empty-state"><div class="loader-spinner" style="margin:0 auto"></div></div>';

  if (State.user?.id) {
    const res = await api(`/orders/${State.user.id}`);
    State.orders = res?.orders || [];
  }

  const statusLabel = { processing: '🔄 В обработке', china: '✈️ Едет из Китая', arrived: '📦 Прибыло', delivered: '🚚 Доставлено', confirmed: '✅ Получено' };
  const statusClass = { processing: 'status-processing', china: 'status-china', arrived: 'status-arrived', delivered: 'status-delivered', confirmed: 'status-confirmed' };

  if (!State.orders.length) {
    el.innerHTML = `<div class="empty-state">
      <div class="empty-state__icon">📦</div>
      <div class="empty-state__title">Заказов нет</div>
      <div class="empty-state__desc">Оформите первый заказ!</div>
      <button class="btn btn-primary" onclick="navigate('catalog')">В каталог</button>
    </div>`;
    return;
  }

  el.innerHTML = State.orders.map((o, i) => `
    <div class="order-card animate-fade delay-${(i % 4) + 1}">
      <div class="order-card__head">
        <span class="order-card__id">Заказ #${o.id}</span>
        <span class="order-status ${statusClass[o.status] || 'status-processing'}">${statusLabel[o.status] || '🔄 В обработке'}</span>
      </div>
      <div style="font-size:14px;font-weight:500;margin-bottom:4px">${o.pname || 'Товар'}</div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:13px;color:var(--text2)">Размер: ${o.size || '—'}</span>
        <span style="font-size:16px;font-weight:700;color:var(--primary)">${fmtPrice(o.price)}</span>
      </div>
      <div style="font-size:12px;color:var(--text3);margin-top:8px">${fmtDate(o.created_at)}</div>
    </div>`).join('');

  // Update profile stats
  document.getElementById('stat-orders').textContent = State.orders.length;
}

// ─── Render Drops ─────────────────────────────────────
function renderDrops() {
  const el = document.getElementById('drops-list');
  if (!el) return;
  // Drops loaded from API
  el.innerHTML = `<div class="empty-state">
    <div class="empty-state__icon">🔥</div>
    <div class="empty-state__title">Скоро дропы</div>
    <div class="empty-state__desc">Следите за обновлениями</div>
    <a href="${State.config?.telegram?.channel || '#'}" class="btn btn-primary" target="_blank">Подписаться на канал</a>
  </div>`;
}

// ─── Render Support ───────────────────────────────────
function renderSupport() {
  const cfg = State.config;
  if (!cfg) return;
  document.querySelectorAll('[data-support-link]').forEach(el => {
    const type = el.dataset.supportLink;
    if (type === 'telegram') el.href = cfg.telegram?.support || cfg.telegram?.channel || '#';
    if (type === 'channel') el.href = cfg.telegram?.channel || '#';
  });
}

// ─── Render About ─────────────────────────────────────
function renderAbout() {
  const cfg = State.config;
  if (!cfg) return;
  const el = document.getElementById('about-name');
  if (el) el.textContent = cfg.shop?.name;
  const el2 = document.getElementById('about-desc');
  if (el2) el2.textContent = cfg.shop?.description;
}

// ─── Render Bonuses ───────────────────────────────────
async function renderBonuses() {
  const el = document.getElementById('bonuses-balance');
  if (!el) return;
  if (State.user?.id) {
    const res = await api(`/profile/${State.user.id}`);
    const bal = res?.profile?.bonus_balance || 0;
    el.textContent = Math.round(bal).toLocaleString('ru-RU');
  } else {
    el.textContent = '0';
  }
}

// ─── Search ───────────────────────────────────────────
function handleSearch(e) {
  State.searchQuery = e.target.value;
  renderProductGrid();
}

// ─── Load data ────────────────────────────────────────
async function loadCatalog() {
  try {
    const res = await api('/categories');
    State.categories = res?.categories || [];
  } catch {}
  try {
    // Load all products from all categories
    const allProds = [];
    for (const cat of State.categories) {
      const res = await api(`/categories/${cat.id}/products`);
      const prods = (res?.products || []).map(p => ({ ...p, category_name: cat.name }));
      allProds.push(...prods);
    }
    State.products = allProds;
  } catch {}
  renderHome();
}

// ─── Apply config styles ──────────────────────────────
function applyConfig(cfg) {
  if (!cfg) return;
  const root = document.documentElement;
  if (cfg.colors) {
    if (cfg.colors.primary) root.style.setProperty('--primary', cfg.colors.primary);
    if (cfg.colors.primary_dark) root.style.setProperty('--primary-dark', cfg.colors.primary_dark);
    if (cfg.colors.primary_light) root.style.setProperty('--primary-light', cfg.colors.primary_light);
    if (cfg.colors.primary_pale) root.style.setProperty('--primary-pale', cfg.colors.primary_pale);
    if (cfg.colors.primary_deep) root.style.setProperty('--primary-deep', cfg.colors.primary_deep);
  }
  // Apply shop name
  document.querySelectorAll('[data-cfg-shopname]').forEach(el => { el.textContent = cfg.shop?.name || ''; });
  document.querySelectorAll('[data-cfg-tagline]').forEach(el => { el.textContent = cfg.shop?.tagline || ''; });
  document.querySelectorAll('[data-cfg-logo]').forEach(el => { if (el.tagName === 'IMG') el.src = cfg.shop?.logo || ''; });
  document.querySelectorAll('[data-cfg-tglink]').forEach(el => { el.href = cfg.telegram?.channel || '#'; });
  // Apply hero
  if (cfg.hero) {
    const t = document.getElementById('hero-title');
    if (t) t.innerHTML = `${cfg.hero.title}<br><span style="color:var(--primary)">${cfg.hero.title_accent}</span> ${cfg.hero.subtitle}`;
    const d = document.getElementById('hero-desc');
    if (d) d.textContent = cfg.hero.description;
    const b1 = document.getElementById('hero-btn-catalog');
    if (b1) b1.textContent = cfg.hero.btn_catalog;
    const b2 = document.getElementById('hero-btn-about');
    if (b2) b2.textContent = cfg.hero.btn_about;
  }
  // Features
  if (cfg.features) {
    const featureIcons = {
      truck: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>`,
      shield: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
      refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>`,
      gift: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 12 20 22 4 22 4 12"/><rect x="2" y="7" width="20" height="5"/><line x1="12" y1="22" x2="12" y2="7"/><path d="M12 7H7.5a2.5 2.5 0 010-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 000-5C13 2 12 7 12 7z"/></svg>`,
    };
    const featEl = document.getElementById('features-inner');
    if (featEl) {
      featEl.innerHTML = cfg.features.map(f => `
        <div class="feature-item">
          <div class="feature-item__icon">${featureIcons[f.icon] || '✨'}</div>
          <div>
            <div class="feature-item__title">${f.title}</div>
            <div class="feature-item__desc">${f.desc}</div>
          </div>
        </div>`).join('');
    }
  }
  // Sale banner
  if (cfg.sale_banner) {
    const st = document.getElementById('sale-title');
    if (st) st.innerHTML = `${cfg.sale_banner.title} <span style="color:var(--primary)">${cfg.sale_banner.percent}</span>`;
    const ss = document.getElementById('sale-sub');
    if (ss) ss.textContent = cfg.sale_banner.subtitle;
    if (cfg.links?.catalog_btn) {
      const sb = document.getElementById('sale-btn');
      if (sb) sb.onclick = () => navigate('catalog');
    }
  }
}

// ─── Load config ──────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch('config.json?v=' + Date.now());
    const cfg = await res.json();
    State.config = cfg;
    State.apiBase = cfg.api?.base_url || '';
    applyConfig(cfg);
  } catch (e) {
    console.error('Config load failed:', e);
    State.config = {};
  }
}

// ─── Init ─────────────────────────────────────────────
async function init() {
  // Telegram
  State.tg = initTelegram();
  const tgUser = State.tg?.initDataUnsafe?.user;
  if (tgUser) {
    State.user = tgUser;
    lsSet('tg_user', tgUser);
  } else {
    // Restore from localStorage if available
    State.user = lsGet('tg_user', null);
  }

  // Load persistent data
  cartLoad();
  favsLoad();
  updateFavBadge();

  // Load config
  await loadConfig();

  // Show loader
  const loader = document.getElementById('app-loader');

  // Load catalog from API
  await loadCatalog();

  // Hide loader
  if (loader) { loader.style.opacity = '0'; setTimeout(() => loader.remove(), 300); }

  // Navigate to home
  navigate('home');

  // Register back button
  if (State.tg?.BackButton) {
    State.tg.BackButton.hide();
  }
}


// ─── Gallery slider controls ──────────────────────────
function galleryGoTo(idx) {
  const items = State._galleryItems || [];
  if (!items.length) return;
  idx = Math.max(0, Math.min(idx, items.length - 1));
  State._galleryIdx = idx;
  const track = document.getElementById('gallery-track');
  if (track) {
    track.style.transform = `translateX(-${idx * (100 / items.length)}%)`;
  }
  // Update dots
  items.forEach((_, i) => {
    const dot = document.getElementById(`gdot-${i}`);
    if (dot) {
      dot.style.width = i === idx ? '18px' : '6px';
      dot.style.background = i === idx ? 'var(--primary)' : 'rgba(255,255,255,0.4)';
    }
  });
  const counter = document.getElementById('gallery-counter');
  if (counter && items.length > 1) counter.textContent = `${idx + 1}/${items.length}`;
}

function galleryNext() {
  const items = State._galleryItems || [];
  galleryGoTo((State._galleryIdx + 1) % items.length);
  State.tg?.HapticFeedback?.selectionChanged?.();
}
function galleryPrev() {
  const items = State._galleryItems || [];
  galleryGoTo((State._galleryIdx - 1 + items.length) % items.length);
  State.tg?.HapticFeedback?.selectionChanged?.();
}

// Touch swipe for gallery
function initGalleryTouch() {
  const slider = document.getElementById('gallery-slider');
  if (!slider) return;
  let startX = 0, isDragging = false;
  slider.addEventListener('touchstart', e => { startX = e.touches[0].clientX; isDragging = true; }, { passive: true });
  slider.addEventListener('touchend', e => {
    if (!isDragging) return;
    isDragging = false;
    const diff = startX - e.changedTouches[0].clientX;
    if (Math.abs(diff) > 40) diff > 0 ? galleryNext() : galleryPrev();
  }, { passive: true });
}

// Override openProduct to init touch after render
const _origOpen = window.openProduct;
window.openProduct = _openProductCore;

// ─── Boot ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);
