# Google Analytics & Conversion Tracking Setup

## Quick Start (5 minutes)

1. Go to **analytics.google.com**
2. Create account: "NarrativeAI" 
3. Property: "narrativeai.myblognow.uk"
4. Create Web data stream
5. Copy your **Measurement ID** (G-XXXXXXXXXX)
6. Replace in your HTML code

---

## Code Implementation

Add to your HTML <head>:
```html
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

---

## Key Events to Track

```javascript
// Page view (automatic)
gtag('event', 'page_view');

// Button clicks
gtag('event', 'click', {
  'event_category': 'engagement',
  'event_label': 'start_free_now'
});

// File upload
gtag('event', 'file_upload', {
  'event_category': 'conversion'
});

// Conversion complete
gtag('event', 'conversion_complete', {
  'event_category': 'conversion'
});
```

---

## Critical Metrics (Track These!)

| Metric | Target | Why |
|--------|--------|-----|
| Bounce Rate | <50% | People engaged |
| Avg Session Duration | >2 min | Content is compelling |
| Upload Rate | >15% | App is discoverable |
| Conversion Rate | 5%+ | Users find value |
| Download Rate | >90% | Happy users |

---

## Monthly Checklist

- ✅ User growth (target: +20% month)
- ✅ Bounce rate trend
- ✅ Conversion rate improvement
- ✅ Traffic source ROI
- ✅ Mobile vs desktop performance
- ✅ Top performing content
