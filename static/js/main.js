// ============================================================
// TheGarden Labs — Main JS
// ============================================================

// NAV SCROLL
const nav = document.getElementById('nav');
if (nav) {
    const onScroll = () => {
        nav.classList.toggle('scrolled', window.scrollY > 20);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
}

// MOBILE BURGER
const burger = document.getElementById('navBurger');
const mobileMenu = document.getElementById('navMobile');
if (burger && mobileMenu) {
    burger.addEventListener('click', () => {
        mobileMenu.classList.toggle('open');
    });
}

// FADE-UP OBSERVER
const fadeEls = document.querySelectorAll('.fade-up');
if (fadeEls.length) {
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach(el => {
                if (el.isIntersecting) {
                    el.target.classList.add('visible');
                    observer.unobserve(el.target);
                }
            });
        },
        { threshold: 0.12 }
    );
    fadeEls.forEach(el => observer.observe(el));
}

// AUTO-HIDE FLASH MESSAGES
const flashes = document.querySelectorAll('.flash');
flashes.forEach(flash => {
    setTimeout(() => {
        flash.style.transition = 'opacity 0.4s ease';
        flash.style.opacity = '0';
        setTimeout(() => flash.remove(), 400);
    }, 5000);
});
