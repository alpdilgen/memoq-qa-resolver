# memoQ QA Resolver — Tasarım Dokümanı (Evrensel)

- **Tarih:** 2026-06-16
- **Durum:** Onaylandı (uygulama planı bekleniyor)
- **Kapsam:** Dile, projeye ve mevcut hata raporuna bağımsız, tüm memoQ projeleri için evrensel QA-issue çözücü.
- **Çekirdek:** Mevcut test edilmiş `inconsistency_resolver` motorundan evrilir (parser, tags, whitespace, apply — 46 test).

---

## 1. Amaç

memoQ'da QA çalıştırıldığında her segmente QA hata/uyarı kodları işlenir (`<mq:warnings40>` → `<mq:errorwarning>`). Bu araç:

1. mqxliff içindeki gömülü QA kodlarını okur (hangi kontrol çalıştıysa — dilden/projeden bağımsız),
2. her uyarılı segmenti AI desteğiyle denetleyip çözümü üretir,
3. **sıfır hata riskiyle** çözebildiklerini otomatik uygular,
4. **insan onayı gerektirenleri** tespit edip bir arayüzde sorun + önerilen çözümü gösterir; kullanıcı onaylar veya (öneri yanlışsa) kendi düzeltip onaylar,
5. düzeltilmiş mqxliff'i üretir (memoQ'ya re-import edilince QA temiz olmalı).

**Hedef:** elle çok uzun sürecek QA düzeltme işini AI + otomasyonla en kısa sürede, hatasız bitirmek.

## 2. İki cephe, tek motor

Sistem hem **bağımsız** çalışacak hem de **AnovaAITool**'a entegre edilecek. Bunu garanti eden ilke: **katı motor/UI ayrımı.**

- **`qa_engine/`** — UI'den ve AI-sağlayıcıdan tamamen bağımsız Python paketi. İçinde `streamlit`, `fastapi`, vb. **yoktur**. Girdi: mqxliff bytes/yol + enjekte AI istemcisi. Çıktı: yapılandırılmış sonuçlar + `apply()`.
- **Cephe 1 — Bağımsız web uygulaması** (FastAPI backend + tarayıcı frontend). Bu sürümde geliştirilir.
- **Cephe 2 — AnovaAITool entegrasyonu** (sonraki faz): `qa_engine`'i import eden bir Streamlit ekranı (`qa_resolver_screen.py`), `verifika_screen.py` desenini taklit eder. Motor buna **hazır** tasarlanır.

### Entegrasyon hedefi hakkında bilinenler (AnovaAITool — github.com/alpdilgen/AnovaAITool)

- Streamlit uygulaması, tek `app.py`, sekmeler: Workspace / Results / Prompt Builder / Verifika QA. Yeni sekme = `app.py`'da bir `st.tabs` satırı + `show_qa_resolver_tab()` çağrısı.
- `utils/xml_parser.py` `XMLParser`: XLIFF/mqxliff parse + `update_xliff()` (memoQ metadata geri yazımı, inline tag `{{N}}` placeholder).
- `services/ai_translator.py` `AITranslator(provider, api_key, model)`: OpenAI **ve** Anthropic destekler (`messages.create`).
- `services/memoq_project_service.py`: SOAP/WSAPI ile `ExportBilingual` → mqxliff bytes; `UpdateTranslationDocumentFromBilingual(projectGuid, fileGuid, XLIFF)` → düzeltilmiş XLIFF'i doğrudan memoQ Server'a geri yaz.
- `models/entities.py`: `TranslationSegment`, `TMMatch`, `TermMatch`. Durum `st.session_state` (senkron, DB yok).
- QA tarafı bugün **Verifika Cloud** (memoQ gömülü kodları değil) — bizim çözücümüz tamamlayıcı ve yeni.

### Motorun entegrasyon-hazırlık gereksinimleri (zorunlu)

1. `qa_engine/` içinde **hiçbir UI importu yok** (streamlit/fastapi yok).
2. **AI erişimi enjekte edilen `AIClient` protokolüyle** — standalone Claude adaptörü; AnovaAITool kendi `AITranslator` adaptörünü verir.
3. **Senkron-uyumlu** (Streamlit senkron çalışır). Engine ana API'si bloklayan/senkron olmalı.
4. Girdi/çıktı **bytes** (veya yol): `analyze(bytes) → ReviewSession`; `apply(bytes, decisions) → fixed_bytes`. Böylece AnovaAITool `last_xliff_bytes`'i doğrudan verir, dönen bytes'ı `memoq_project_service` ile geri yazar.
5. Motor kendi sağlam mqxliff parser'ını kullanır (kaçış/tail/bpt hataları zaten düzeltildi) — entegrasyonda AnovaAITool sadece bytes besler.

## 3. Resolver registry & sözleşme

Çekirdek soyutlama: her QA **koduna** bir **Resolver** eşleyen bir registry.

```
Resolver.resolve(issue, segment, context) -> Resolution
Resolution = {
  action: "fix" | "ignore" | "report",
  new_target: str | None,     # action=fix ise düzeltilmiş hedef (tokenized→detokenized, geçerli XML)
  confidence: float,          # 0.0–1.0
  needs_approval: bool,       # True → onay kuyruğuna
  rationale: str,
}
```

- **Issue:** `{code, problemname, args, segmentguid, tu_id}` — gömülü `<mq:errorwarning>`'dan parse edilir.
- **Segment:** kaynak/hedef (tokenized + tag haritası), status, TM eşleşmesi, komşu segmentler.
- **Strateji tipleri:**
  - `deterministic` — uyarı verisinden kesin düzeltme, AI'sız (örn. fazla boşluğu sil). Kanıtlanabilir doğru → `needs_approval=False`.
  - `ai` — dilbilimsel yargı; Claude çağrısı; güven + (riskli kodlarda) adversarial doğrulama → yüksekse otomatik, değilse onay.
  - `report_only` — otomatik düzeltme riskli; `action="report"`, asla otomatik uygulanmaz.
- **Kod politikası override:** bir config (per-code) her kodun stratejisini/aksiyonunu ve güven eşiğini override edebilir (evrensel araç farklı projelere uyarlanır).
- **Bilinmeyen kod:** registry'de yoksa → `report_only` (güvenli varsayılan).

## 4. Kod → strateji haritası (risk katmanlı)

memoQ taksonomisi (kodlar `concepts-quality-assurance-qa-warnings.html`'den). **Hatalar (1xxx/2xxx) yok sayılamaz** — düzeltilmeli; **uyarılar (3xxx) yok sayılabilir.**

| Strateji | Kodlar | Not |
|---|---|---|
| **deterministic (oto)** | 3050 (çoklu boşluk), 3071–3076 (işaret etrafı boşluk/nbsp), 3110 (segment sonu boşluk), 3190–3197 (tag etrafı boşluk/nbsp), 3065 (full-width rakam), 3069 (sayı gruplama) | Çoğunlukla mevcut whitespace motorundan; uyarı verisi + kaynak-hizalama ile kesin |
| **ai (yüksek-güven oto, değilse onay)** | 3100/3101 (tutarsızlık — mevcut), 3091–3098 (terminoloji), 3020 (bitiş noktalama), 3030 (ilk harf), 3085 (dupe kelime), 3061/3067/3068 (sayı format) | Locale kuralları hedef-dilden |
| **ai ama varsayılan onay/report** | 1001/1002, 2004, 2010, 2011, 2015, 2016 (tag yapısı — yerleştirme riskli), 3062/3063/3064 (sayı eşleşmez/eksik/fazla), 3040 (hedef=kaynak), 3010 (boş hedef) | Yapısal/anlamsal risk yüksek; AI önerir, insan onaylar |
| **report_only** | 3081–3084, 3180 (uzunluk), 3161/3162 (yazım/dilbilgisi), 3151–3153 (match farkı), 3200–3206 (regex), 3120 (yasak karakter) | Otomatik düzeltme güvenli değil; raporla |

Bu harita registry'de **veri** olarak tanımlanır; yeni kod eklemek = registry'ye bir satır + (gerekiyorsa) bir resolver fonksiyonu.

## 5. Segment yönlendirme & güven ("sıfır hata")

QA çalıştırılmış mqxliff → parse → her uyarılı segment için ilgili Resolver(ler) çağrılır:

- **deterministic** → hesapla, doğrula (tag/XML geçerliliği), otomatik uygula.
- **ai** → Claude segmenti denetler, `Resolution` döner. Riskli kodlarda öneri **adversarial doğrulamadan** geçer (bağımsız "bu düzeltme doğru mu / çürüt" adımı). Güven ≥ eşik **ve** doğrulama geçerse otomatik; değilse `needs_approval=True`.
- **report_only** → onay kuyruğuna (insan).

"Sıfır hata" güvencesi: deterministik = yapısal kesin; AI = yalnızca yüksek-güven + doğrulanmış olanlar otomatik; belirsiz/riskli her şey insana. Hiçbir bozuk-tag/geçersiz-XML yazılmaz (apply öncesi bellekte doğrulama).

**Hacim/performans:** on binlerce boşluk uyarısı AI'ya gitmez (deterministik, ücretsiz, anında). Yalnızca yargı gerektiren küçük azınlık AI'ya gider → hız + maliyet kontrolü.

## 6. Web onay arayüzü (Cephe 1, bağımsız)

FastAPI backend + tarayıcı frontend. Akış:

1. **Yükle** — `.mqxliff` (gömülü QA kodlu).
2. **QA Çöz** — motor çalışır, ilerleme gösterilir.
3. **Sonuç ekranı:**
   - **Otomatik uygulananlar** (deterministik + yüksek-güven AI): kod bazında özet sayım + gözden geçirilebilir liste.
   - **Onay bekleyenler**: her satır → kod, kaynak, mevcut hedef, **önerilen düzeltme (fark vurgulu)**, gerekçe, güven; **Onayla / Düzenle / Reddet**. Kullanıcı onaylar veya düzeltip onaylar.
4. **Sonlandır** → otomatik + onaylananlar uygulanır → `FIXED.mqxliff` indirilir (+ orijinal yedeği).

UI, motorun `ReviewSession` çıktısını render eder; kullanıcı kararları motora geri verilir (`apply`). Bu akış, entegrasyonda Streamlit ekranıyla birebir eşlenebilir (aynı `ReviewSession` veri sözleşmesi).

## 7. Apply & memoQ I/O

- **Standalone birincil:** dosya yükle/indir. Hedefli, segmentguid-anahtarlı düzenleme (BOM/biçim korunur); apply öncesi bellekte XML doğrulama; orijinal `.bak`.
- **Entegrasyon (sonraki faz):** AnovaAITool, `apply`'dan dönen bytes'ı `memoq_project_service.UpdateTranslationDocumentFromBilingual` ile doğrudan memoQ Server'a geri yazar.
- false_positive/ignore: `mq:errorwarning-ignored="errorwarning-ignored"` işaretlenir (uyarı kayar). fix: hedef metni güncellenir + çözülen uyarı kaldırılır.

## 8. AI sağlayıcı soyutlaması

`AIClient` protokolü (örn. `resolve(prompt, schema) -> dict`). Adaptörler:
- **Standalone:** Claude Opus 4.8 (Anthropic), `output_config.format` ile şema-zorunlu, adaptive thinking, prompt-cache.
- **AnovaAITool:** mevcut `AITranslator(provider, api_key, model)` sarmalayan adaptör (OpenAI veya Anthropic).

Motor sağlayıcıyı bilmez; yalnızca `AIClient` arayüzünü çağırır.

## 9. Mevcut çekirdeğin yeniden kullanımı

`inconsistency_resolver` modülleri `qa_engine` çekirdeği olur:
- `parser.py` (gömülü warnings + source/target inner-XML, kaçış-güvenli), `tags.py` (tokenize/detokenize), `whitespace.py` (tag-boundary hizalama → deterministik resolver'ların temeli), `apply.py` (hedefli yazım + doğrulama), `models.py`, `ai.py` (Claude adaptörü). 46 test korunur/genişletilir.
- Yeni: `registry.py` (kod→resolver), `resolvers/` (deterministik + AI resolver'lar), `engine.py` (analyze/apply orchestration, ReviewSession), `aiclient.py` (protokol + Claude adaptörü), `webapp/` (FastAPI + frontend).

## 10. Kapsam ve fazlama

"Tüm kodlar" = registry çerçevesi + risk haritası + artımlı resolver'lar.
- **Faz 1 (bu sürüm):** Motor çekirdeği (registry, engine, AIClient), deterministik whitespace/nbsp/full-width/gruplama resolver'ları, mevcut AI tutarsızlık resolver'ı, report_only varsayılanı; bağımsız FastAPI web UI; dosya yükle/çöz/onayla/indir.
- **Faz 2:** Ek AI resolver'lar (terminoloji, noktalama, ilk-harf, dupe, sayı format) + adversarial doğrulama.
- **Faz 3:** Tag-yapısı resolver'ları (onay-varsayılan) + AnovaAITool Streamlit entegrasyonu + memoQ Server SOAP round-trip.

## 11. Kapsam dışı

- LQA (insan değerlendirmesi) — ayrı.
- Kaynak metni değiştirme (kaynak kilitli).
- Otomatik çeviri/uzunluk kısaltma (report_only).
- AnovaAITool'a kod taşıma (Faz 1'de değil; motor hazır olur).

## 12. Açık doğrulama noktaları

1. Tag-yapısı (2011 eksik tag yerleştirme) için AI'nın güvenli yerleştirme yapabilirliği — Faz 3'te değerlendirilecek; emin olunmazsa report_only kalır.
2. Locale-bazlı sayı/nbsp kurallarının (örn. Fransızca nbsp) hedef-dilden doğru türetilmesi.
3. Çözülen uyarı öğesini kaldırma vs. ignore — memoQ re-import + QA-yeniden-çalıştırma ile doğrulanır (kabul testi).
4. `AIClient` protokol imzasının hem Claude (`messages.create` + structured output) hem `AITranslator.translate_batch` ile temiz örtüşmesi.
