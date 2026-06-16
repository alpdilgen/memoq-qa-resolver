# Inconsistency Resolver — Tasarım Dokümanı

- **Tarih:** 2026-06-15
- **Durum:** Onaylandı (uygulama planı bekleniyor)
- **Hedef girdi örneği:** `check_gre.mqxliff` (memoQ XLIFF 1.2, EN→EL, 2.321 segment)
- **Çıktı:** Tekrar kullanılabilir Python aracı (CLI)

---

## 1. Amaç

QA'lı bir memoQ `.mqxliff` dosyasındaki **tutarsızlık (inconsistency)** uyarılarını, yapay zeka (Claude Opus 4.8) kullanarak çözen tekrar kullanılabilir bir araç. Araç:

1. mqxliff içine gömülü QA uyarılarını okur,
2. sorunlu segmentleri ve mevcut çevirileri analiz eder,
3. her vaka için doğru aksiyonu belirler (daha iyi çeviriyi seç / farklılaştır / yanlış alarmı yok say),
4. **önce bir rapor üretir** (hiçbir şey yazmadan),
5. onaydan sonra düzeltilmiş bir mqxliff üretir.

Düzeltilmiş dosya memoQ'ya import edilip QA yeniden çalıştırıldığında inconsistency uyarısı kalmamalıdır.

## 2. Problem analizi (gerçek veriye dayalı)

`check_gre.mqxliff` üzerinde yapılan inceleme:

- Toplam **2.256 uyarı**, üç tipte:
  - `inconsistent translation` — **2.240** (kategori id=2)
  - `best exact/context match is different from translation` — 10
  - `Duplicate words` — 6
- Inconsistency uyarıları iki yöne ayrılıyor:
  - **Hedef-tutarsızlığı** ("The target segment is also the translation of…") — ~2.214: *aynı Yunanca hedef, farklı İngilizce kaynak*.
  - **Kaynak-tutarsızlığı** ("The same segment was also translated as…") — ~26: *aynı kaynak, farklı hedef*.
- 2.214 hedef-uyarısı pratikte **yalnızca ~24 gruba** sıkışmış; büyük çoğunluğu **yanlış alarm**:
  - Kaynakta sondaki boşluk farkı (`Color box: ` vs `Color box:`),
  - Kaynakta yazım hatası (`Bliser card` vs `Blister card`),
  - Boşluk/noktalama varyasyonu (`Premium Comfort ` vs `Premium Comfort`).
- Azınlık ama **gerçek hata** vakaları da var, örn. `Ocean Deep Sand` ve `Ocean Deep Sage` ikisi de aynı (yanlış) Yunancaya çevrilmiş → ayrıştırılması gerekiyor.

**Sonuç:** "Mevcut çevirilerden iyisini seç ve uygula" mantığı vakaların yalnızca bir kısmına uyar. Tasarım üç sınıfı da kapsar.

### memoQ uyarı ve ignore mekaniği

- Uyarılar dosyada inline gömülü: `<trans-unit>` içinde `<mq:warnings40>` → `<mq:errorwarning …>`.
- İlgili attribute'lar: `mq:errorwarning-code`, `-problemname`, `-longdesc`, `-localizationargs` (çatışan kaynak/hedef çiftini sekmeyle ayırır), `-ignorable`, `-ignored`.
- memoQ bir uyarıyı **`mq:errorwarning-ignored="errorwarning-ignored"`** ile "yok sayıldı" işaretleyebiliyor (dosyada zaten 2 örnek mevcut, kategori 7). Bu, false-positive'leri çeviriye dokunmadan susturmanın mekanizmasıdır.
- mqxliff zaten her segmentte `<mq:insertedmatch source="…" matchrate="…">` ile TM eşleşmesini taşıyor — TM bağlamı için ek dosya gerekmez.

## 3. Karar bağlamı (AI neye dayanır)

Bir çevirinin "daha iyi" olduğuna veya yeni çevirinin doğruluğuna karar verirken AI şu bağlamları kullanır:

1. **Glossary / termbase** (opsiyonel, dosya yolu verilirse),
2. **Translation Memory** — mqxliff içindeki `<mq:insertedmatch>` verisi,
3. **Dosya-içi sıklık/tutarlılık** — bir varyant en çok hangi biçimde kullanılmış,
4. **Komşu segment bağlamı** — ürün açıklaması akışı, segment türü (renk adı, özellik başlığı vb.).

## 4. Yüksek seviye mimari

Standalone Python paketi, iki fazlı CLI:

```
inconsistency_resolver/
  __init__.py
  cli.py          # `analyze` ve `apply` alt komutları
  parser.py       # mqxliff → trans-unit + warning modeli (raw-XML konumları korunur)
  casebuilder.py  # uyarıları "vaka"lara grupla + bağlam topla
  glossary.py     # opsiyonel terim sözlüğü / termbase yükle
  ai.py           # Claude Opus 4.8 çağrısı, structured output, prompt cache
  report.py       # HTML rapor + decisions.json üret
  apply.py        # kararları mqxliff'e işle (tag-güvenli), yedekle, doğrula
  models.py       # ortak veri sınıfları (Case, Member, Decision)
tests/
  fixtures/       # sentetik küçük mqxliff golden dosyaları
docs/superpowers/specs/2026-06-15-inconsistency-resolver-design.md
```

- **Dil/çalışma ortamı:** Python 3.11+, Windows. Bağımlılık: `anthropic` SDK. Stdlib: `re`/dikkatli string işleme + `xml.etree`/`lxml` (parse için; yazımda hedefli string düzenleme).
- **API anahtarı:** `ANTHROPIC_API_KEY` ortam değişkeninden. Hardcode edilmez.
- **Model:** `claude-opus-4-8`, `thinking: {"type": "adaptive"}`, `output_config.format` ile şema-zorunlu JSON çıktı. Sabit sistem talimatı + glossary `cache_control: {"type":"ephemeral"}` ile cache'lenir.

## 5. Veri akışı

```
mqxliff
  → parse  (trans-unit'ler: id, segmentguid, source/target iç-XML, inline tag'ler, TM, status, warnings)
  → vaka oluştur:
        - hedef-tutarsızlığı: normalize(target) → birden çok farklı kaynak
        - kaynak-tutarsızlığı: normalize(source) → birden çok farklı hedef
  → bağlam ekle (komşu segmentler, TM eşleşmesi, glossary, dosya-içi sıklık, mekanik kaynak-diff)
  → AI (vaka başına 1 çağrı, structured output)
  → decisions.json + report.html        ← FAZ 1 biter; HİÇBİR ŞEY YAZILMAZ
        … kullanıcı raporu inceler / decisions.json'ı opsiyonel düzenler / onaylar …
  → apply(decisions.json, mqxliff)       ← FAZ 2
  → check_gre.FIXED.mqxliff  +  check_gre.mqxliff.bak
```

## 6. Veri modeli

```
Member {
  tu_id, segmentguid,
  source_text_tokenized,   # inline tag'ler {1}{2}.. token'larına soyutlanmış
  target_text_tokenized,
  source_tags, target_tags,# token → orijinal tag XML eşlemesi
  status, tm_match,        # <mq:insertedmatch> varsa
  warning_refs             # bu segmentteki ilgili <mq:errorwarning> öğelerine işaretçiler
}

Case {
  id,
  type: "target_inconsistency" | "source_inconsistency",
  members: [Member, ...],
  distinct_sources, distinct_targets,   # sayım/frekansla
  mechanical_diff                        # false-positive adayları için kaynaklar arası fark
}

Decision {
  case_id,
  category: "false_positive" | "pick_best" | "differentiate" | "needs_manual",
  rationale, confidence: "high"|"medium"|"low",
  chosen_member_id,        # pick_best: tam <target> XML'i kopyalanacak segment
  differentiated: [ {source_key, new_target_tokenized} ],  # differentiate
  # false_positive: metin değişmez; warning_refs'ler ignored işaretlenir
}
```

## 7. AI sözleşmesi

**Vaka başına bir çağrı.** Girdi (cache'lenen sabit kısım + vaka-özel kısım):

- Sabit (cache'li): rol/talimat, üç kategori tanımı, tag-token kuralları, glossary (varsa).
- Vaka-özel: vaka tipi; her farklı kaynak/hedef varyantı + frekansı; komşu segment örnekleri; TM önerisi; mekanik kaynak-diff özeti.

**Inline tag'ler `{1} {2} …` token'larına soyutlanır**; AI metni bozamaz, token'ları korumakla yükümlüdür.

**Çıktı şeması (`output_config.format` / `messages.parse`):**

| alan | tip | açıklama |
|---|---|---|
| `category` | enum | `false_positive` \| `pick_best` \| `differentiate` |
| `rationale` | string | Kısa, somut gerekçe (false_positive için farkın türü dahil) |
| `confidence` | enum | `high` \| `medium` \| `low` |
| `chosen_variant_key` | string? | pick_best: hangi mevcut hedef varyantı daha iyi |
| `differentiated` | array? | differentiate: `[{source_key, new_target}]`, token'lar korunarak |

- **pick_best**'te AI metin **üretmez**, yalnızca mevcut bir varyantı seçer → seçilen segmentin tam `<target>` XML'i kopyalanır (sıfır tag riski).
- **differentiate**'te AI yeni hedef metni üretir; token'lar zorunlu korunur.
- **false_positive**'te metin değişmez.

## 8. mqxliff yazma mekaniği

12MB, BOM'lu UTF-8 dosya. **Hedefli, segmentguid-anahtarlı düzenleme** — tüm dosya yeniden serialize edilmez; BOM, biçim, satır sonları korunur (büyük dosyaları python ile düzenleme prensibine uygun).

| Aksiyon | Uygulama |
|---|---|
| **pick_best** | Seçilen üyenin `<target …>…</target>` iç-XML'i (tag'ler dahil) vakanın tüm üyelerinin `<target>`'ına yazılır. Çözülen `inconsistent translation` uyarı öğesi kaldırılır. |
| **differentiate** | Token'lar orijinal tag XML'ine geri çevrilip yeni `<target>` yazılır. Çözülen uyarı öğesi kaldırılır. |
| **false_positive** | Metne dokunulmaz; ilgili `<mq:errorwarning>` öğelerine `mq:errorwarning-ignored="errorwarning-ignored"` eklenir. |

- Çıktı **yeni dosyaya** yazılır: `check_gre.FIXED.mqxliff`. Orijinal `check_gre.mqxliff.bak` olarak yedeklenir. Asla yerinde değiştirilmez.
- `needs_manual` ve (varsayılan) `low` güvenli vakalara dokunulmaz; raporda işaretli kalır.

### Round-trip riski (uygulama sırasında doğrulanacak)

Hedef metni değiştirmek memoQ tarafında segmenti "edited" yapar; `mq:status`/commit timestamp'leri korunur. Ignored bayrağının segment değişince memoQ tarafından korunup korunmadığı **gerçek import testi** ile doğrulanmalı (Bölüm 11 kabul testi). Gerekirse apply, değişen segmentlerde status/percent alanlarını da güncelleyecek şekilde genişletilir.

## 9. Rapor

İki çıktı:

1. **`report.html`** — insan-okunur. Vaka başına: tip, segment numaraları, kaynak/hedef varyantları, AI kararı, gerekçe, güven.
2. **`decisions.json`** — makine-okunur, **apply'ın tek doğruluk kaynağı**. Kullanıcı isterse elle düzenleyip kararları override edebilir.

### False-positive şeffaflığı (kullanıcı talebi)

Her `false_positive` vakası için rapor şunları açıkça gösterir:

- İlgili **segment numaraları** (tu_id) ve segmentguid'ler,
- Kaynaklar arası **mekanik fark** (vurgulanmış): "sondaki boşluk", "yazım hatası: `Bliser` → `Blister`", "noktalama farkı" vb.,
- AI'nın **gerekçesi**.

Yani hem otomatik tespit edilen fark hem AI yorumu yan yana sunulur — körlemesine ignore yapılmaz.

Rapor ayrıca özet sayım verir: kaç vaka false_positive / pick_best / differentiate / needs_manual / low-confidence.

## 10. Hata yönetimi

- **API hatası:** SDK otomatik retry (429/5xx). Vaka-bazlı izolasyon — başarısız vaka rapora `needs_manual` düşer, araç çökmez.
- **Tag/token uyuşmazlığı:** AI çıktısındaki token'lar kaynak token kümesiyle eşleşmezse karar reddedilir, `needs_manual` işaretlenir; bozuk tag'li hedef **asla** yazılmaz.
- **Düşük güven:** `confidence=low` otomatik uygulanmaz; raporda ayrı. FAZ 2'de `--include-low` ile zorlanabilir.
- **İdempotluk:** `analyze` salt-okunur. `apply` çıktı dosyası varsa `--force` olmadan üzerine yazmaz.
- **Uygulama sonrası doğrulama:** çıktı yeniden parse edilir → (a) XML iyi-biçimli mi, (b) değiştirilmeyen segmentlerde tag sayıları korunmuş mu, (c) differentiate'te token kümesi tutarlı mı.

## 11. Test / kabul ölçütü

- **Birim testleri:** parser; vaka gruplama (normalize kuralları); tag↔token round-trip; ignore-bayrağı enjeksiyonu; decisions.json → apply.
- **Golden:** bilinen vakalar içeren küçük sentetik mqxliff (her üç kategori + needs_manual).
- **Kabul testi (kullanıcı):** `check_gre.FIXED.mqxliff` memoQ'ya import → QA yeniden çalıştır → **sıfır inconsistency uyarısı**. Nihai başarı ölçütü budur.

## 12. CLI arayüzü (taslak)

```
python -m inconsistency_resolver analyze <input.mqxliff> \
    [--glossary <path>] [--out-dir <dir>] [--model claude-opus-4-8]
# → report.html + decisions.json

python -m inconsistency_resolver apply <input.mqxliff> <decisions.json> \
    [--out <output.mqxliff>] [--include-low] [--force]
# → *.FIXED.mqxliff + *.bak
```

## 13. Kapsam dışı (YAGNI)

- `Duplicate words` ve `best exact/context match` uyarıları bu sürümde çözülmez (yalnızca raporda bilgi olarak listelenebilir). Odak: inconsistency.
- Kaynak metni düzeltme (kaynak QA'da kilitli; boşluk/yazım kaynak farkları false-positive olarak ignore edilir, kaynağa dokunulmaz).
- memoQ projesine doğrudan entegrasyon yok; yalnızca mqxliff dosya alışverişi.

## 13a. Hedef kenar-boşluğu normalizasyonu (deterministik, eklenti)

**Bulgu:** Gerçek dosyada 2.321 segmentin **692'sinde** hedef, kaynakta olmayan baş/son boşluklar içeriyor (TM artığı, genelde 10'ar boşluk; 638'i aynı zamanda inconsistency uyarısı taşıyor). Örn. kaynak `[bpt]Mattress:[ept][ph]`, hedef `··········[bpt]Στρώμα:[ept][ph]··········`. Bunlar yanlış alarm **değil**, düzeltilmeli.

**Çözüm — deterministik ön-geçiş (AI gerektirmez):**
- **Kural:** Hedefin baştaki/sondaki `[ space/tab ]` dizisi, kaynağınkiyle **birebir eşitlenir** (kaynakta yoksa silinir, varsa o kadar bırakılır). İç boşluklara ve `nbsp` (`\xa0`) dışındaki/dahili metne **dokunulmaz**. İç boşluk farkları (örn. `Στρώμα:··········[ph]`) AI'nın inconsistency kararına bırakılır.
- **Kapsam:** Tüm segmentler (uyarı taşısın taşımasın).
- **Akış:** `analyze` ayrıştırmadan sonra düzeltmeleri hesaplar (`whitespace_fixes`), vakaları **normalize edilmiş** hedefler üzerinden kurar (saf boşluk-tutarsızlıkları böylece çöker, AI'ya gitmez), raporda ayrı bir bölümde segment no + önce/sonra listeler. `decisions.json` artık `{"whitespace_fixes": [...], "decisions": {...}}` biçimindedir. `apply` önce kenar-boşluğu düzeltmelerini ham `<target>` kenarlarına uygular, sonra AI kararlarını. `settarget` kararı zaten normalize hedefi içerir; `false_positive` segmentleri hem kenar düzeltmesi alır hem `ignored` işaretlenir.

## 14. Açık doğrulama noktaları (uygulamada netleşecek)

1. Ignored bayrağının segment metni değişen vakalarda memoQ tarafından korunması (import testi).
2. Çözülen uyarı öğesini kaldırmak vs. olduğu gibi bırakmak — memoQ QA yeniden hesapladığı için ikisi de güvenli; temizlik için kaldırma tercih edilir, import testiyle doğrulanır.
3. `lxml` ile mi yoksa konum-bazlı string düzenleme ile mi yazılacağı — BOM/biçim korunması ölçüt; golden testle karara bağlanır.
