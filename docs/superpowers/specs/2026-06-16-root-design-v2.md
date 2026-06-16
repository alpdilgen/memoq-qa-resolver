# memoQ QA Resolver — Root Design v2

- **Tarih:** 2026-06-16
- **Durum:** Onaylandı (uygulama planı bekleniyor)
- **Amaç:** Aracı, tespit edilen her QA hatasını eksiksiz hesaba katan, tutarsızlığı doğru çözen ve tag'leri memoQ gibi okunabilir gösterip güvenle geri yazan sağlam bir temele oturtmak.
- **Bağlam:** Mevcut `qa_engine` (90 test) üzerine inşa; üç temel ayak.

---

## İlke 1 — Issue-Ledger (korunum / conservation)

**Değişmez kural:** Dosyada tespit edilen **X** hata için (X = dosyadaki `<mq:errorwarning>` sayısı):
```
X = (otomatik düzeltilen) + (ignore edilen) + (onay bekleyen/onaylanan)
```
Her hata **tam olarak bir** sonuç kovasına düşer; hiçbiri sessizce atlanmaz. Onaylar bittiğinde her hata FIX veya IGNORE olur → re-QA ~0 (etkin düzeltmeler + meşru ignore'lar).

**Tasarım sonuçları:**
- **Hata-bazlı defter.** Her `<mq:errorwarning>` bir `Issue`. Motor X Issue'yu deftere yazar; her birine tam bir `outcome` (`fix` | `ignore` | `needs_approval`) atar. İşleme segment-bazlı olabilir ama **muhasebe hata-bazlıdır** (bir segmentin tek kararı, o segmentteki tüm hatalarına atfedilir).
- **Sessiz atlama yasak.** "İşaretli ama değişecek bir şey yok / zaten doğru" → bu bir **false positive → IGNORE** (kovaya girer). Deterministik no-op artık atlanmaz; FIX (değişiklik varsa) ya da IGNORE (yoksa) olur.
- **Mutabakat zorunlu.** Motor `reconcile()` ile `fix + ignore + needs_approval == X` olduğunu **assert eder**; tutmazsa hata fırlatır (kaçan issue = bug). UI başlıkta `X = A + B + C` gösterir.
- **Dürüstlük.** Gerçek ama otomatik çözülemeyen hata **zorla ignore edilmez**; `needs_approval` olarak açık/sayılı kalır (kullanıcı çözer). Gerçek hatayı gizlemek yasak.

## İlke 2 — Segment-üstü tutarsızlık (3100/3101)

Tutarsızlık doğası gereği **cross-segment**: aynı kaynak belgede farklı çevrilmiş. Per-segment AI bunu çözemez (gördüğümüz Maxmor/MaxMor/nokta karmaşası). Çözüm:

- **Gruplama:** Tüm segmentleri tara; aynı (tokenize) kaynağa sahip ve 3100/3101 işaretli olanları grupla.
- **Kanonik seçim:** Her grup için AI (veya dosya-içi çoğunluk) **tek standart hedef formu** seçer.
- **Uygulama:** Grubun tüm üyelerinin hedefi kanonik forma sabitlenir → tutarlı → uyarı kapanır.
- **Akış:** Bu, segment-bazlı geçişten ÖNCE bir **karar** üretir (her ilgili segment için "hedef = kanonik"). Segment-bazlı geçiş tek yazıcıdır ve bu kararı uygular (çakışma yok).
- Güven yüksekse otomatik; değilse onay.

## İlke 3 — Okunabilir tag katmanı

Ham inline-tag XML'i (`<bpt id="1">&lt;g id="71" mmq78catalogvalue=...&gt;</bpt>`) ne kullanıcı ne AI doğru okuyabiliyor; `⟦N⟧` opak markerları da sızınca dosyayı bozuyor. memoQ'nun gösterdiği temiz etiket zaten tag'in **`mmq78catalogvalue`** alanında (`<cf size=9.5>`, `</strong>`, `<li>` …).

- **Etiket türetme:** Her inline tag için `mmq78catalogvalue`'dan (çift-unescape) memoQ-tarzı okunabilir etiket çıkarılır; yoksa tag tipine göre fallback (`<g>`, `</g>`, `<x/>`).
- **Token biçimi:** İç token benzersiz id + okunabilir etiket taşır, örn. `⟦1:</strong>⟧`. detokenize **id'ye göre** tam tag XML'ine çevirir (etiket kısmı yalnızca okunurluk için).
- **UI:** Segment, memoQ gibi okunabilir etiketlerle/çiplerle gösterilir ve düzenlenir.
- **AI:** Aynı okunabilir etiketler verilir ("bu etiketleri koru ve doğru yerleştir") — ham XML/opak marker yerine. Bu, AI'nın **tag'leri doğru yerleştirmesini** sağlar (2011/2016 tag hatalarını kökten azaltır).
- **Yazma:** Etiketler tam tag XML'ine geri çevrilir (round-trip). apply, çıktıda kalan herhangi bir token (`⟦`/`⟧`) varsa o segmenti **yazmaz** (güvenlik ağı) — dosya asla bozulmaz.

---

## Bütünleşik akış

```
mqxliff (X errorwarning)
  → parse: Issues[] + Members (tag map + okunabilir etiketler)
  → Phase A (cross-segment): 3100/3101 gruplarını topla → AI kanonik formu seçer → her ilgili segment için "hedef=kanonik" kararı
  → Phase B (per-segment): her segment için, o segmentin TÜM hatalarını ele alan tek karar:
        - bulk-deterministik (tag-kenarı boşluk, 3050 daraltma) → fix
        - Phase A kararı varsa → hedef=kanonik
        - aksi halde AI (okunabilir etiketlerle) → fix | ignore(false-positive) | needs_approval
  → Ledger: her Issue'ya outcome atanır; reconcile: fix+ignore+needs_approval == X
  → ReviewSession: auto_fixed / ignored / needs_approval  (+ X mutabakatı)
        … kullanıcı onay/düzenleme …
  → apply: outcome'ları uygula (tag round-trip; token sızıntısı yazılmaz; XML doğrula)
  → FIXED.mqxliff
```

## Mevcut çekirdeğe etkisi
- `models.py`: `Issue.outcome` alanı + `ReviewSession` mutabakat sayıları.
- `tags.py`: okunabilir etiket türetme + `⟦id:label⟧` token biçimi + id-bazlı detokenize.
- `parser.py`: tag map'e okunabilir etiketleri ekle.
- `engine.py`: hata-bazlı ledger; Phase A (cross-segment) + Phase B; reconcile assert; no-op→ignore.
- `resolvers/`: cross-segment inconsistency resolver (geri gelir, kanonik seçim); ai_segment_resolver okunabilir etiket kullanır; whitespace resolver 3050 iç-daraltma ekler.
- `apply.py`: id-bazlı round-trip; token-sızıntısı guard (mevcut); genel ignore (mevcut).
- `streamlit_app.py`: mutabakat başlığı (X=A+B+C) + okunabilir etiketler.

## Korunan davranışlar (regresyon yok)
- Marker/korunum guard (apply çıktıda token yazmaz).
- XML doğrulama (apply öncesi bellekte).
- Riskli tag kodları (2010/2011/2015/2016) → her zaman onay.
- false-positive → ignore (çeviri değişmez).

## Kapsam dışı / sonraki
- AnovaAITool entegrasyonu (motor hazır; ayrı faz).
- Performans: büyük dosyada Phase B AI çağrılarının gruplanması (gerekirse).

## Açık doğrulama noktaları
1. `mmq78catalogvalue` her tag tipinde okunabilir etiket veriyor mu (açılış/kapanış/self-closing) — gerçek dosyalarda doğrula.
2. Cross-segment kanonik seçimin re-QA'da 3100/3101'i gerçekten kapatması (import testi).
3. Reconcile assert'inin gerçek dosyada her zaman tutması (kaçan issue olmaması).
