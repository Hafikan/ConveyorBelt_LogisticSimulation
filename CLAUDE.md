# CLAUDE.md - Proje Bağlamı

Bu dosya, Claude Code'un projeyle çalışırken kullanacağı bağlam bilgilerini içerir.

## Proje Özeti

Konveyör bant lojistik simülasyonu - SimPy tabanlı discrete event simulation. Farklı hızlara sahip multi-segment konveyör hatları ve birden fazla feeder line ile kapasite/koordinasyon problemlerini analiz eder.

## Mimari

### Core Bileşenler

```
src/core/
├── packet.py         # Paket veri modeli (pozisyon, boyut, kaynak, bekleme süresi)
├── conveyor.py       # Tek segment konveyör (geriye uyumluluk için)
├── conveyor_line.py  # Multi-segment konveyör hattı (ana sınıf)
└── feeder.py         # Feeder Line - paket üretici ve aktarıcı
```

### Ana Simülasyon

```
src/main_multiline.py  # Ana simülasyon dosyası (multi-segment destekli)
```

## Multi-Segment Konveyör Sistemi

### Segment Yapısı

Her segment farklı hıza ve yöne sahip olabilir:

```python
class ConveyorSegment:
    id: str              # "SEGMENT_1", "SEGMENT_2", ...
    length: float        # Metre
    speed: float         # Metre/saniye
    direction: str       # "horizontal" veya "vertical"
    start_offset: float  # Global pozisyon (hat başından)
```

### 2D Layout

Segmentler sıralı bağlanır:
- Horizontal segmentler X ekseninde ilerler
- Vertical segmentler Y ekseninde ilerler
- Yön değişimlerinde layout otomatik hesaplanır

### Mevcut Konfigürasyon (6 Segment)

```
SEGMENT_1 (3m, 0.5m/s, horizontal) → Giriş Bölgesi
SEGMENT_2 (3m, 1.0m/s, horizontal) → Hızlı Taşıma
SEGMENT_3 (3m, 0.3m/s, horizontal) → Tarama İstasyonu (DARBOĞAZ!)
SEGMENT_4 (3m, 0.6m/s, vertical)   → Dikey Yükselme
SEGMENT_5 (3m, 0.8m/s, vertical)   → Dikey Çıkış
SEGMENT_6 (3m, 0.7m/s, horizontal) → Çıkış Bölgesi
```

**Toplam:** 18 metre, 18 paket kapasitesi

### Feeder Konfigürasyonu (3 Feeder)

```
FEEDER_A: 0.4 p/s, Segment 0 (pozisyon: 1.5m)
FEEDER_B: 0.3 p/s, Segment 1 (pozisyon: 4.5m)
FEEDER_C: 0.25 p/s, Segment 2 (pozisyon: 7.5m) - DARBOĞAZ SEGMENTİNDE
```

## Konfigürasyon

`config/simulation.toml` dosyasında:

```toml
# Segment tanımı
[[conveyor_segments]]
id = "SEGMENT_1"
length = 3.0
speed = 0.5
direction = "horizontal"  # veya "vertical"
description = "Giriş Bölgesi"

# Feeder tanımı
[[feeders]]
id = "FEEDER_A"
production_rate = 0.4
connection_segment = 0     # Segment index (0-based)
connection_offset = 1.5    # Segment başından mesafe
```

## Komutlar

```bash
# Simülasyonu çalıştır
.venv/bin/python src/main_multiline.py

# Çıktılar
output/plots/
├── executive_dashboard.png   # KPI dashboard
├── multisegment_layout.png   # 2D sistem layoutu
├── multisegment_analysis.png # Segment analizi
└── snapshot_frames.png       # Zaman serisi snapshot'ları
```

## Görselleştirmeler

### Otomatik Oluşturulan Grafikler

1. **Executive Dashboard** - Feeder verimliliği, segment dolulukları, throughput
2. **System Layout** - 2D görünüm (horizontal + vertical segmentler)
3. **Snapshot Frames** - 1 saniyelik aralıklarla anlık görüntüler
4. **Analysis** - Segment bazlı detaylı analiz

### Feeder Durumu Gösterimi

- **Yeşil border**: Aktif feeder
- **Sarı border (#FFD700)**: Bloke feeder (paket aktaramıyor)

## Önemli Notlar

### Darboğaz Analizi

SEGMENT_3 (0.3 m/s) ciddi darboğaz oluşturur:
- Önceki segmentlerden gelen paketler yığılır
- FEEDER_C bu segmentte olduğu için çok düşük verimlilik (%3-5)

### Kapasite Hesaplama

```
Segment Kapasitesi = length / (packet_length + min_gap)
                   = 3.0 / (0.3 + 0.5) = 3.75 ≈ 3 paket
```

### Performans İpuçları

- Yavaş segmentler darboğaz yaratır
- Feeder'ları darboğaz segmentlerine koymaktan kaçının
- Segment hızlarını dengeleyerek throughput artırılabilir

## Dosya Yapısı

```
ConveyorBelt_LogisticSimulation/
├── config/
│   └── simulation.toml      # Ana konfigürasyon
├── src/
│   ├── core/
│   │   ├── packet.py
│   │   ├── conveyor.py
│   │   ├── conveyor_line.py # Multi-segment sistem
│   │   └── feeder.py
│   └── main_multiline.py    # Ana simülasyon
├── output/plots/            # Grafikler
├── CLAUDE.md               # Bu dosya
└── README.md               # Proje dokümantasyonu
```

## Geliştirme Geçmişi

1. **İterasyon 1**: Tek konveyör + tek feeder
2. **İterasyon 2**: Tek konveyör + çoklu feeder + görselleştirmeler
3. **İterasyon 3**: Multi-segment konveyör + 2D layout + vertical segmentler
