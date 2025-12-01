"""
İTERASYON 3: Multi-Segment Conveyor Line
Farklı hızlara sahip segment'lerden oluşan konveyör hattı simülasyonu
"""

import simpy
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.animation as animation
from typing import List
import sys
from pathlib import Path
import tomllib

# Core sınıfları import et
sys.path.append(str(Path(__file__).parent))
from core.conveyor_line import ConveyorLine
from core.feeder import FeederLine


def load_config(config_path: Path = None) -> dict:
    """TOML config dosyasını yükler."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "simulation.toml"

    with open(config_path, "rb") as f:
        return tomllib.load(f)


class MultiSegmentSimulation:
    """Multi-segment konveyör hattı simülasyonu"""

    def __init__(self, config: dict = None):
        self.config = config if config is not None else load_config()
        self.env = simpy.Environment()
        self.conveyor_line: ConveyorLine = None
        self.feeders: List[FeederLine] = []
        self.snapshots = []

        # Visualization config
        vis_cfg = self.config.get('visualization', {})
        self.FEEDER_COLORS = vis_cfg.get('colors', {
            'FEEDER_A': '#E74C3C',
            'FEEDER_B': '#3498DB',
            'FEEDER_C': '#2ECC71',
            'FEEDER_D': '#F39C12',
        })
        self.SEGMENT_COLORS = vis_cfg.get('segment_colors', {
            'slow': '#E74C3C',
            'normal': '#3498DB',
            'fast': '#2ECC71',
        })

        self.output_dir = Path(__file__).parent.parent / vis_cfg.get('output_dir', 'output/plots')
        self.dpi = vis_cfg.get('dpi', 150)

        # Dark tema
        theme = vis_cfg.get('theme', 'dark')
        if theme == 'dark':
            plt.style.use('dark_background')

    def setup(self):
        """Simülasyonu hazırla"""
        print("🏗️  Multi-Segment Sistem kuruluyor...")

        # Config'den paket ayarları
        pkt_cfg = self.config.get('packet', {})
        min_gap = pkt_cfg.get('min_gap', 0.5)
        default_packet_length = pkt_cfg.get('default_length', 0.3)

        # Conveyor Line oluştur
        self.conveyor_line = ConveyorLine(
            env=self.env,
            id="MAIN_LINE",
            min_gap=min_gap,
            default_packet_length=default_packet_length
        )

        # Segment'leri ekle
        segments_cfg = self.config.get('conveyor_segments', [])
        print(f"\n✅ Konveyör Hattı Segment'leri:")
        for seg_cfg in segments_cfg:
            segment = self.conveyor_line.add_segment(
                id=seg_cfg['id'],
                length=seg_cfg['length'],
                speed=seg_cfg['speed'],
                description=seg_cfg.get('description', ''),
                direction=seg_cfg.get('direction', 'horizontal')
            )
            dir_symbol = "↔" if segment.direction == "horizontal" else "↕"
            print(f"   {segment.id} {dir_symbol}:")
            print(f"      Uzunluk: {segment.length}m")
            print(f"      Hız: {segment.speed} m/s")
            print(f"      Yön: {segment.direction}")
            print(f"      Pozisyon: {segment.start_offset}m - {segment.end_offset}m")
            print(f"      Açıklama: {segment.description}")

        print(f"\n📏 Toplam Hat Uzunluğu: {self.conveyor_line.total_length}m")
        print(f"📦 Toplam Kapasite: {self.conveyor_line.capacity} paket")

        # Feeder'ları oluştur
        print(f"\n✅ Feeder Lines:")
        for feeder_cfg in self.config.get('feeders', []):
            # Global giriş pozisyonunu hesapla
            segment_idx = feeder_cfg.get('connection_segment', 0)
            offset = feeder_cfg.get('connection_offset', 0.0)
            entry_position = self.conveyor_line.get_global_entry_position(segment_idx, offset)

            feeder = FeederLine(
                env=self.env,
                id=feeder_cfg['id'],
                target_conveyor=self.conveyor_line,
                production_rate=feeder_cfg['production_rate'],
                entry_position=entry_position,
                max_queue_size=feeder_cfg.get('max_queue_size', 100)
            )
            self.feeders.append(feeder)

            segment = self.conveyor_line.segments[segment_idx] if segment_idx < len(self.conveyor_line.segments) else None
            print(f"   {feeder.id}:")
            print(f"      Üretim hızı: {feeder.production_rate:.3f} paket/s ({1.0/feeder.production_rate:.1f}s aralıkla)")
            print(f"      Bağlantı: Segment {segment_idx} ({segment.id if segment else 'N/A'})")
            print(f"      Global Pozisyon: {entry_position}m")

    def snapshot_collector(self):
        """Belirli aralıklarla sistem durumunu kaydet"""
        interval = self.config['simulation']['snapshot_interval']
        while True:
            snapshot = {
                'time': self.env.now,
                'conveyor_line': {
                    'packets': [
                        {
                            'id': p.id,
                            'position': p.position,
                            'source': p.source_feeder
                        }
                        for p in self.conveyor_line.packets_in_transit
                    ],
                    'utilization': self.conveyor_line.get_utilization(),
                    'total_processed': self.conveyor_line.total_packets_processed,
                    'segments': [
                        {
                            'id': s.id,
                            'packets': len(s.packets),
                            'utilization': s.get_utilization()
                        }
                        for s in self.conveyor_line.segments
                    ]
                },
                'feeders': []
            }

            for feeder in self.feeders:
                snapshot['feeders'].append({
                    'id': feeder.id,
                    'queue_length': len(feeder.queue),
                    'is_blocked': feeder.is_blocked,
                    'total_produced': feeder.total_produced,
                    'total_transferred': feeder.total_transferred
                })

            self.snapshots.append(snapshot)
            yield self.env.timeout(interval)

    def run(self, duration: float = None):
        """Simülasyonu çalıştır"""
        if duration is None:
            duration = self.config['simulation']['duration']

        print(f"\n🚀 Simülasyon başlıyor... (Süre: {duration} saniye)")
        print("=" * 70)

        # Process'leri başlat
        self.env.process(self.snapshot_collector())

        for feeder in self.feeders:
            self.env.process(feeder.start_production())
            self.env.process(feeder.transfer_process())

        # Simülasyonu çalıştır
        self.env.run(until=duration)

        print("=" * 70)
        print(f"\n✅ Simülasyon tamamlandı!")

    def print_statistics(self):
        """Detaylı istatistikleri yazdır"""
        print("\n" + "=" * 70)
        print("📊 SİMÜLASYON İSTATİSTİKLERİ")
        print("=" * 70)

        stats = self.conveyor_line.get_statistics()
        print(f"\n🎯 KONVEYÖR HATTI: {stats['id']}")
        print(f"   Toplam Uzunluk: {stats['total_length']}m")
        print(f"   Segment Sayısı: {stats['segment_count']}")
        print(f"   Toplam işlenen paket: {stats['total_processed']}")
        print(f"   Halen üzerinde: {stats['packets_in_transit']} paket")
        print(f"   Son doluluk oranı: {stats['utilization']:.2%}")

        print(f"\n📊 SEGMENT DETAYLARI:")
        for seg in stats['segments']:
            print(f"   {seg['id']} ({seg['description']}):")
            print(f"      Uzunluk: {seg['length']}m, Hız: {seg['speed']} m/s")
            print(f"      Paket: {seg['packets']}, Doluluk: {seg['utilization']:.2%}")

        print(f"\n📦 FEEDER LINES:")
        for feeder in self.feeders:
            fstats = feeder.get_statistics()
            print(f"\n   {fstats['id']}:")
            print(f"      Üretilen: {fstats['total_produced']} paket")
            print(f"      Aktarılan: {fstats['total_transferred']} paket")
            print(f"      Kuyrukta: {fstats['current_queue']} paket")
            print(f"      Toplam bloke süresi: {fstats['total_blocked_time']:.1f}s")
            print(f"      Verimlilik: {fstats['utilization_rate']:.2%}")

        print("\n" + "=" * 70)

    def get_segment_color(self, speed: float) -> str:
        """Hıza göre segment rengi döndürür"""
        if speed <= 0.4:
            return self.SEGMENT_COLORS.get('slow', '#E74C3C')
        elif speed >= 0.8:
            return self.SEGMENT_COLORS.get('fast', '#2ECC71')
        else:
            return self.SEGMENT_COLORS.get('normal', '#3498DB')

    def calculate_segment_positions(self):
        """
        Her segment'in 2D düzlemdeki başlangıç ve bitiş koordinatlarını hesaplar.
        Yatay segment'ler X ekseninde, dikey segment'ler Y ekseninde ilerler.

        Returns:
            List of dict: Her segment için {start_x, start_y, end_x, end_y, direction}
        """
        positions = []
        current_x = 0.0
        current_y = 10.0  # Başlangıç Y pozisyonu

        for segment in self.conveyor_line.segments:
            if segment.direction == "horizontal":
                end_x = current_x + segment.length
                end_y = current_y
            else:  # vertical
                end_x = current_x
                end_y = current_y + segment.length  # Yukarı doğru

            positions.append({
                'segment': segment,
                'start_x': current_x,
                'start_y': current_y,
                'end_x': end_x,
                'end_y': end_y,
                'direction': segment.direction
            })

            current_x = end_x
            current_y = end_y

        return positions

    def get_packet_2d_position(self, global_position: float, segment_positions: list):
        """
        Paketin global pozisyonundan 2D koordinatını hesaplar.

        Args:
            global_position: Hat üzerindeki pozisyon (metre)
            segment_positions: calculate_segment_positions() çıktısı

        Returns:
            (x, y) koordinatları
        """
        for pos in segment_positions:
            seg = pos['segment']
            if seg.start_offset <= global_position < seg.end_offset:
                # Bu segment içinde
                local_pos = global_position - seg.start_offset
                ratio = local_pos / seg.length

                x = pos['start_x'] + ratio * (pos['end_x'] - pos['start_x'])
                y = pos['start_y'] + ratio * (pos['end_y'] - pos['start_y'])
                return (x, y, pos['direction'])

        # Son segment'in sonunda
        if segment_positions:
            last = segment_positions[-1]
            return (last['end_x'], last['end_y'], last['direction'])

        return (0, 10, 'horizontal')

    def visualize_system_layout(self):
        """Sistem mimarisini göster - dikey segment desteği ile"""
        fig, ax = plt.subplots(figsize=(18, 12))
        fig.patch.set_facecolor('#1a1a1a')
        ax.set_facecolor('#1a1a1a')

        # Segment pozisyonlarını hesapla
        segment_positions = self.calculate_segment_positions()

        # Konveyör genişliği
        belt_width = 1.5

        # Segment'leri çiz
        for pos in segment_positions:
            segment = pos['segment']
            color = self.get_segment_color(segment.speed)

            if pos['direction'] == 'horizontal':
                # Yatay segment
                seg_rect = patches.Rectangle(
                    (pos['start_x'], pos['start_y'] - belt_width/2),
                    segment.length,
                    belt_width,
                    linewidth=2,
                    edgecolor='#555555',
                    facecolor=color,
                    alpha=0.6
                )
                ax.add_patch(seg_rect)

                # Segment etiketi (üstte)
                mid_x = (pos['start_x'] + pos['end_x']) / 2
                ax.text(mid_x, pos['start_y'] + belt_width/2 + 0.8,
                       f"{segment.id}\n{segment.speed} m/s",
                       ha='center', va='bottom', fontsize=9, color='white',
                       fontweight='bold')

                # Akış yönü oku
                ax.annotate('', xy=(pos['end_x'] - 0.3, pos['start_y']),
                           xytext=(pos['start_x'] + 0.3, pos['start_y']),
                           arrowprops=dict(arrowstyle='->', color='white', lw=1.5, alpha=0.7))
            else:
                # Dikey segment
                seg_rect = patches.Rectangle(
                    (pos['start_x'] - belt_width/2, pos['start_y']),
                    belt_width,
                    segment.length,
                    linewidth=2,
                    edgecolor='#555555',
                    facecolor=color,
                    alpha=0.6
                )
                ax.add_patch(seg_rect)

                # Segment etiketi (sağda)
                mid_y = (pos['start_y'] + pos['end_y']) / 2
                ax.text(pos['start_x'] + belt_width/2 + 0.8, mid_y,
                       f"{segment.id}\n{segment.speed} m/s",
                       ha='left', va='center', fontsize=9, color='white',
                       fontweight='bold')

                # Akış yönü oku (yukarı)
                ax.annotate('', xy=(pos['start_x'], pos['end_y'] - 0.3),
                           xytext=(pos['start_x'], pos['start_y'] + 0.3),
                           arrowprops=dict(arrowstyle='->', color='white', lw=1.5, alpha=0.7))

        # Feeder'ları çiz
        for feeder in self.feeders:
            # Feeder'ın 2D pozisyonunu bul
            fx, fy, fdir = self.get_packet_2d_position(feeder.entry_position, segment_positions)
            color = self.FEEDER_COLORS.get(feeder.id, '#FFFFFF')

            if fdir == 'horizontal':
                # Feeder alttan bağlanır - merkez fx'te
                feeder_width = 0.8
                feeder_height = 2.5
                feeder_rect = patches.Rectangle(
                    (fx - feeder_width/2, fy - belt_width/2 - feeder_height),
                    feeder_width, feeder_height,
                    linewidth=2, edgecolor=color, facecolor=color, alpha=0.8
                )
                ax.add_patch(feeder_rect)

                # Bağlantı çizgisi (feeder'dan konveyöre)
                ax.plot([fx, fx], [fy - belt_width/2 - feeder_height, fy - belt_width/2],
                       color=color, linewidth=2, linestyle='--', alpha=0.6)

                # Giriş noktası işareti
                ax.plot(fx, fy, 'o', color=color, markersize=6, zorder=5)

                ax.text(fx, fy - belt_width/2 - feeder_height - 0.5, feeder.id,
                       ha='center', va='top', fontsize=10,
                       fontweight='bold', color=color)
            else:
                # Dikey segment'e soldan bağlanır - merkez fy'de
                feeder_width = 2.5
                feeder_height = 0.8
                feeder_rect = patches.Rectangle(
                    (fx - belt_width/2 - feeder_width, fy - feeder_height/2),
                    feeder_width, feeder_height,
                    linewidth=2, edgecolor=color, facecolor=color, alpha=0.8
                )
                ax.add_patch(feeder_rect)

                # Bağlantı çizgisi
                ax.plot([fx - belt_width/2 - feeder_width, fx - belt_width/2],
                       [fy, fy], color=color, linewidth=2, linestyle='--', alpha=0.6)

                # Giriş noktası işareti
                ax.plot(fx, fy, 'o', color=color, markersize=6, zorder=5)

                ax.text(fx - belt_width/2 - feeder_width - 0.5, fy, feeder.id,
                       ha='right', va='center', fontsize=10,
                       fontweight='bold', color=color)

        # Son snapshot'taki paketler
        if self.snapshots:
            last_snapshot = self.snapshots[-1]
            for pkt_data in last_snapshot['conveyor_line']['packets']:
                glob_pos = pkt_data['position']
                px, py, pdir = self.get_packet_2d_position(glob_pos, segment_positions)
                color = self.FEEDER_COLORS.get(pkt_data['source'], '#FFFFFF')

                if pdir == 'horizontal':
                    pkt_rect = patches.Rectangle(
                        (px - 0.2, py - 0.4), 0.4, 0.8,
                        linewidth=1, edgecolor=color, facecolor=color, alpha=0.9
                    )
                else:
                    pkt_rect = patches.Rectangle(
                        (px - 0.4, py - 0.2), 0.8, 0.4,
                        linewidth=1, edgecolor=color, facecolor=color, alpha=0.9
                    )
                ax.add_patch(pkt_rect)

        # Başlangıç ve bitiş noktaları
        if segment_positions:
            start_pos = segment_positions[0]
            end_pos = segment_positions[-1]
            ax.plot(start_pos['start_x'], start_pos['start_y'], 'o',
                   color='#2ECC71', markersize=15, label='Giriş', zorder=10)
            ax.plot(end_pos['end_x'], end_pos['end_y'], 'o',
                   color='#E74C3C', markersize=15, label='Çıkış', zorder=10)

        # Bilgi kutusu
        info_text = "SEGMENT BİLGİLERİ\n" + "─" * 25 + "\n"
        for seg in self.conveyor_line.segments:
            dir_symbol = "↔" if seg.direction == "horizontal" else "↕"
            info_text += f"\n{seg.id} {dir_symbol}:\n"
            info_text += f"  {seg.description}\n"
            info_text += f"  Uzunluk: {seg.length}m\n"
            info_text += f"  Hız: {seg.speed} m/s\n"

        ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
               fontsize=9, fontfamily='monospace', color='white',
               verticalalignment='top', horizontalalignment='left',
               bbox=dict(boxstyle='round,pad=0.5', facecolor='#222222',
                        edgecolor='#555555', alpha=0.9))

        # Legend için hız renkleri
        legend_elements = [
            patches.Patch(facecolor=self.SEGMENT_COLORS['slow'], label='Yavaş (≤0.4 m/s)'),
            patches.Patch(facecolor=self.SEGMENT_COLORS['normal'], label='Normal'),
            patches.Patch(facecolor=self.SEGMENT_COLORS['fast'], label='Hızlı (≥0.8 m/s)')
        ]
        ax.legend(handles=legend_elements, loc='lower right', fontsize=9,
                 facecolor='#222222', edgecolor='#555555')

        # Eksen limitlerini hesapla
        if segment_positions:
            all_x = [p['start_x'] for p in segment_positions] + [p['end_x'] for p in segment_positions]
            all_y = [p['start_y'] for p in segment_positions] + [p['end_y'] for p in segment_positions]
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)
            # Feeder'lar için ekstra margin
            ax.set_xlim(min_x - 5, max_x + 5)
            ax.set_ylim(min_y - 5, max_y + 5)

        ax.set_xlabel('X (metre)', fontsize=12, color='white')
        ax.set_ylabel('Y (metre)', fontsize=12, color='white')
        ax.set_title(f'Multi-Segment Konveyör Hattı (Toplam: {self.conveyor_line.total_length}m)',
                    fontsize=14, fontweight='bold', color='white')
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.2, color='#555555')
        ax.tick_params(colors='white')

        plt.tight_layout()
        output_path = self.output_dir / 'multisegment_layout.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"\n📊 Sistem düzeni kaydedildi: {output_path}")
        plt.show()

    def visualize_live(self, interval_ms: int = 500, save_gif: bool = False):
        """Canlı animasyon - dikey segment desteği ile"""
        if not self.snapshots:
            print("⚠️  Snapshot bulunamadı!")
            return

        fig, ax = plt.subplots(figsize=(14, 14))
        fig.patch.set_facecolor('#1a1a1a')

        # Segment pozisyonlarını bir kez hesapla
        segment_positions = self.calculate_segment_positions()
        belt_width = 1.2

        # Eksen limitlerini hesapla
        all_x = [p['start_x'] for p in segment_positions] + [p['end_x'] for p in segment_positions]
        all_y = [p['start_y'] for p in segment_positions] + [p['end_y'] for p in segment_positions]
        min_x, max_x = min(all_x) - 5, max(all_x) + 5
        min_y, max_y = min(all_y) - 5, max(all_y) + 5

        def update(frame_idx):
            ax.clear()
            ax.set_facecolor('#1a1a1a')

            snapshot = self.snapshots[frame_idx]
            time = snapshot['time']

            # Segment'leri çiz
            for i, pos in enumerate(segment_positions):
                segment = pos['segment']
                color = self.get_segment_color(segment.speed)
                seg_data = snapshot['conveyor_line']['segments'][i]

                if pos['direction'] == 'horizontal':
                    seg_rect = patches.Rectangle(
                        (pos['start_x'], pos['start_y'] - belt_width/2),
                        segment.length, belt_width,
                        linewidth=2, edgecolor='#555555', facecolor=color, alpha=0.5
                    )
                    ax.add_patch(seg_rect)
                    mid_x = (pos['start_x'] + pos['end_x']) / 2
                    ax.text(mid_x, pos['start_y'] + belt_width/2 + 0.3,
                           f"{segment.speed}m/s", ha='center', fontsize=8, color='white')
                    ax.text(mid_x, pos['start_y'] - belt_width/2 - 0.3,
                           f"{seg_data['packets']}pkt", ha='center', fontsize=8,
                           color=color, va='top')
                else:
                    seg_rect = patches.Rectangle(
                        (pos['start_x'] - belt_width/2, pos['start_y']),
                        belt_width, segment.length,
                        linewidth=2, edgecolor='#555555', facecolor=color, alpha=0.5
                    )
                    ax.add_patch(seg_rect)
                    mid_y = (pos['start_y'] + pos['end_y']) / 2
                    ax.text(pos['start_x'] + belt_width/2 + 0.3, mid_y,
                           f"{segment.speed}m/s", ha='left', fontsize=8, color='white')
                    ax.text(pos['start_x'] - belt_width/2 - 0.3, mid_y,
                           f"{seg_data['packets']}pkt", ha='right', fontsize=8,
                           color=color)

            # Feeder'lar
            for i, feeder in enumerate(self.feeders):
                fx, fy, fdir = self.get_packet_2d_position(feeder.entry_position, segment_positions)
                color = self.FEEDER_COLORS.get(feeder.id, '#FFFFFF')
                feeder_data = snapshot['feeders'][i]
                is_blocked = feeder_data.get('is_blocked', False)

                edge_color = '#FFD700' if is_blocked else color
                line_width = 4 if is_blocked else 2

                if fdir == 'horizontal':
                    feeder_rect = patches.Rectangle(
                        (fx - 0.3, fy - belt_width/2 - 2), 0.6, 2,
                        linewidth=line_width, edgecolor=edge_color,
                        facecolor=color, alpha=0.7
                    )
                    ax.add_patch(feeder_rect)
                    label_y = fy - belt_width/2 - 2.5
                    label_va = 'top'
                    label_ha = 'center'
                    label_x = fx
                else:
                    feeder_rect = patches.Rectangle(
                        (fx - belt_width/2 - 2, fy - 0.3), 2, 0.6,
                        linewidth=line_width, edgecolor=edge_color,
                        facecolor=color, alpha=0.7
                    )
                    ax.add_patch(feeder_rect)
                    label_x = fx - belt_width/2 - 2.5
                    label_y = fy
                    label_va = 'center'
                    label_ha = 'right'

                label_color = '#FFD700' if is_blocked else color
                status = "BEKL" if is_blocked else ""
                queue_info = f"Q:{feeder_data['queue_length']}" if feeder_data['queue_length'] > 0 else ""
                ax.text(label_x, label_y, f"{feeder.id[-1]}{status}\n{queue_info}",
                       ha=label_ha, va=label_va, fontsize=7, color=label_color)

            # Paketler
            for pkt in snapshot['conveyor_line']['packets']:
                px, py, pdir = self.get_packet_2d_position(pkt['position'], segment_positions)
                color = self.FEEDER_COLORS.get(pkt['source'], '#FFFFFF')

                if pdir == 'horizontal':
                    pkt_rect = patches.Rectangle(
                        (px - 0.15, py - 0.3), 0.3, 0.6,
                        linewidth=1, edgecolor=color, facecolor=color, alpha=0.9
                    )
                else:
                    pkt_rect = patches.Rectangle(
                        (px - 0.3, py - 0.15), 0.6, 0.3,
                        linewidth=1, edgecolor=color, facecolor=color, alpha=0.9
                    )
                ax.add_patch(pkt_rect)

            # Başlangıç/bitiş
            if segment_positions:
                start_pos = segment_positions[0]
                end_pos = segment_positions[-1]
                ax.plot(start_pos['start_x'], start_pos['start_y'], 'o',
                       color='#2ECC71', markersize=10, zorder=10)
                ax.plot(end_pos['end_x'], end_pos['end_y'], 'o',
                       color='#E74C3C', markersize=10, zorder=10)

            # Bilgi paneli
            pkt_count = len(snapshot['conveyor_line']['packets'])
            utilization = snapshot['conveyor_line']['utilization']
            processed = snapshot['conveyor_line']['total_processed']

            info_text = f"t={time:.1f}s\n"
            info_text += f"Hat: {pkt_count}\n"
            info_text += f"Islenen: {processed}\n"
            info_text += f"Doluluk: {utilization:.0%}"

            ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                   fontsize=10, fontfamily='monospace', color='white',
                   verticalalignment='top',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='#222222',
                            edgecolor='#555555', alpha=0.9))

            # Progress bar (üstte)
            progress = (frame_idx + 1) / len(self.snapshots)
            total_time = self.snapshots[-1]['time']
            bar_width = max_x - min_x - 2
            prog_rect = patches.Rectangle(
                (min_x + 1, max_y - 1), progress * bar_width, 0.3,
                facecolor='#2ECC71', alpha=0.8
            )
            ax.add_patch(prog_rect)
            ax.text((min_x + max_x) / 2, max_y - 0.3,
                   f'İlerleme: {progress:.0%} (t={time:.0f}s / {total_time:.0f}s)',
                   ha='center', fontsize=9, color='white')

            ax.set_xlim(min_x, max_x)
            ax.set_ylim(min_y, max_y)
            ax.set_xlabel('X (metre)', fontsize=11, color='white')
            ax.set_ylabel('Y (metre)', fontsize=11, color='white')
            ax.set_title(f'CANLI - Multi-Segment Konveyor Hatti',
                        fontsize=14, fontweight='bold', color='#E74C3C')
            ax.set_aspect('equal')
            ax.tick_params(colors='white')
            ax.grid(True, alpha=0.2, color='#555555')

            return []

        anim = animation.FuncAnimation(
            fig, update,
            frames=len(self.snapshots),
            interval=interval_ms,
            blit=False,
            repeat=True
        )

        if save_gif:
            output_path = self.output_dir / 'multisegment_live.gif'
            print(f"📹 GIF kaydediliyor: {output_path}")
            anim.save(output_path, writer='pillow', fps=1000//interval_ms, dpi=80)
            print(f"✅ GIF kaydedildi: {output_path}")

        plt.tight_layout()
        print("▶️  Canlı simülasyon başlatılıyor...")
        plt.show()

    def visualize_speed_impact(self):
        """Segment hızlarının paket akışına etkisini göster"""
        if not self.snapshots:
            return

        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        fig.patch.set_facecolor('#1a1a1a')

        # 1. Segment dolulukları zaman içinde
        ax1 = axes[0, 0]
        ax1.set_facecolor('#1a1a1a')

        times = [s['time'] for s in self.snapshots]
        for i, segment in enumerate(self.conveyor_line.segments):
            utilizations = [s['conveyor_line']['segments'][i]['utilization'] * 100
                          for s in self.snapshots]
            color = self.get_segment_color(segment.speed)
            ax1.plot(times, utilizations, label=f"{segment.id} ({segment.speed}m/s)",
                    color=color, linewidth=2)

        ax1.set_xlabel('Zaman (s)', color='white')
        ax1.set_ylabel('Doluluk (%)', color='white')
        ax1.set_title('Segment Dolulukları', fontsize=12, fontweight='bold', color='white')
        ax1.legend(facecolor='#222222', edgecolor='#555555')
        ax1.grid(True, alpha=0.2, color='#555555')
        ax1.tick_params(colors='white')

        # 2. Toplam paket sayısı
        ax2 = axes[0, 1]
        ax2.set_facecolor('#1a1a1a')

        packet_counts = [len(s['conveyor_line']['packets']) for s in self.snapshots]
        processed = [s['conveyor_line']['total_processed'] for s in self.snapshots]

        ax2.plot(times, packet_counts, label='Hatta', color='#3498DB', linewidth=2)
        ax2.plot(times, processed, label='İşlenen (Toplam)', color='#2ECC71', linewidth=2)
        ax2.fill_between(times, packet_counts, alpha=0.3, color='#3498DB')

        ax2.set_xlabel('Zaman (s)', color='white')
        ax2.set_ylabel('Paket Sayısı', color='white')
        ax2.set_title('Paket Akışı', fontsize=12, fontweight='bold', color='white')
        ax2.legend(facecolor='#222222', edgecolor='#555555')
        ax2.grid(True, alpha=0.2, color='#555555')
        ax2.tick_params(colors='white')

        # 3. Segment başına paket dağılımı (son durum)
        ax3 = axes[1, 0]
        ax3.set_facecolor('#1a1a1a')

        if self.snapshots:
            last = self.snapshots[-1]
            seg_names = [f"{s['id']}\n({self.conveyor_line.segments[i].speed}m/s)"
                        for i, s in enumerate(last['conveyor_line']['segments'])]
            seg_packets = [s['packets'] for s in last['conveyor_line']['segments']]
            colors = [self.get_segment_color(self.conveyor_line.segments[i].speed)
                     for i in range(len(seg_names))]

            bars = ax3.bar(seg_names, seg_packets, color=colors, alpha=0.8)
            for bar, count in zip(bars, seg_packets):
                ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                        str(count), ha='center', color='white', fontweight='bold')

        ax3.set_ylabel('Paket Sayısı', color='white')
        ax3.set_title('Segment Başına Paket (Son Durum)', fontsize=12, fontweight='bold', color='white')
        ax3.grid(True, alpha=0.2, color='#555555', axis='y')
        ax3.tick_params(colors='white')

        # 4. Feeder istatistikleri
        ax4 = axes[1, 1]
        ax4.set_facecolor('#1a1a1a')
        ax4.axis('off')

        summary = "📊 ÖZET İSTATİSTİKLER\n" + "=" * 35 + "\n\n"

        stats = self.conveyor_line.get_statistics()
        summary += f"Hat Toplam Uzunluk: {stats['total_length']}m\n"
        summary += f"Toplam İşlenen: {stats['total_processed']} paket\n"
        summary += f"Hatta Kalan: {stats['packets_in_transit']} paket\n\n"

        summary += "Segment Hızları:\n"
        for seg in self.conveyor_line.segments:
            travel_time = seg.length / seg.speed
            summary += f"  {seg.id}: {seg.length}m / {seg.speed}m/s = {travel_time:.1f}s\n"

        summary += f"\nFeeder Durumu:\n"
        for feeder in self.feeders:
            fstats = feeder.get_statistics()
            summary += f"  {fstats['id']}: {fstats['total_transferred']}/{fstats['total_produced']} aktarıldı\n"

        ax4.text(0.1, 0.9, summary, transform=ax4.transAxes,
                fontsize=10, fontfamily='monospace', color='white',
                verticalalignment='top',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#222222',
                         edgecolor='#555555', alpha=0.9))

        plt.suptitle('Multi-Segment Analiz', fontsize=14, fontweight='bold', color='white')
        plt.tight_layout()

        output_path = self.output_dir / 'multisegment_analysis.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"📊 Analiz kaydedildi: {output_path}")
        plt.show()

    def visualize_snapshot_frames(self, max_frames: int = 30):
        """Snapshot'ları frame-by-frame gösterir (2D layout ile)"""
        num_snapshots = min(len(self.snapshots), max_frames)
        if num_snapshots == 0:
            print("⚠️  Snapshot bulunamadı!")
            return

        segment_positions = self.calculate_segment_positions()
        belt_width = 1.0

        # Eksen limitlerini hesapla
        all_x = [p['start_x'] for p in segment_positions] + [p['end_x'] for p in segment_positions]
        all_y = [p['start_y'] for p in segment_positions] + [p['end_y'] for p in segment_positions]
        min_x, max_x = min(all_x) - 4, max(all_x) + 4
        min_y, max_y = min(all_y) - 4, max(all_y) + 4

        # Grid boyutunu hesapla
        cols = 6
        rows = (num_snapshots + cols - 1) // cols

        fig, axes = plt.subplots(rows, cols, figsize=(24, rows * 4))
        fig.patch.set_facecolor('#1a1a1a')
        axes = axes.flatten() if num_snapshots > 1 else [axes]

        for idx in range(len(axes)):
            ax = axes[idx]
            ax.set_facecolor('#1a1a1a')

            if idx < num_snapshots:
                snapshot = self.snapshots[idx]

                # Segment'leri çiz
                for pos in segment_positions:
                    segment = pos['segment']
                    color = self.get_segment_color(segment.speed)

                    if pos['direction'] == 'horizontal':
                        seg_rect = patches.Rectangle(
                            (pos['start_x'], pos['start_y'] - belt_width/2),
                            segment.length, belt_width,
                            linewidth=1, edgecolor='#555555', facecolor=color, alpha=0.5
                        )
                    else:
                        seg_rect = patches.Rectangle(
                            (pos['start_x'] - belt_width/2, pos['start_y']),
                            belt_width, segment.length,
                            linewidth=1, edgecolor='#555555', facecolor=color, alpha=0.5
                        )
                    ax.add_patch(seg_rect)

                # Feeder'lar - bloke olanlar sarı border ile gösterilir
                for i, feeder in enumerate(self.feeders):
                    fx, fy, fdir = self.get_packet_2d_position(feeder.entry_position, segment_positions)
                    color = self.FEEDER_COLORS.get(feeder.id, '#FFFFFF')
                    feeder_data = snapshot['feeders'][i]
                    is_blocked = feeder_data.get('is_blocked', False)

                    edge_color = '#FFD700' if is_blocked else color
                    line_width = 3 if is_blocked else 1

                    if fdir == 'horizontal':
                        feeder_rect = patches.Rectangle(
                            (fx - 0.3, fy - belt_width/2 - 1.5), 0.6, 1.5,
                            linewidth=line_width, edgecolor=edge_color, facecolor=color, alpha=0.6
                        )
                    else:
                        feeder_rect = patches.Rectangle(
                            (fx - belt_width/2 - 1.5, fy - 0.3), 1.5, 0.6,
                            linewidth=line_width, edgecolor=edge_color, facecolor=color, alpha=0.6
                        )
                    ax.add_patch(feeder_rect)

                # Paketler
                for pkt in snapshot['conveyor_line']['packets']:
                    px, py, pdir = self.get_packet_2d_position(pkt['position'], segment_positions)
                    color = self.FEEDER_COLORS.get(pkt['source'], '#FFFFFF')

                    if pdir == 'horizontal':
                        pkt_rect = patches.Rectangle(
                            (px - 0.15, py - 0.3), 0.3, 0.6,
                            linewidth=1, edgecolor=color, facecolor=color, alpha=0.9
                        )
                    else:
                        pkt_rect = patches.Rectangle(
                            (px - 0.3, py - 0.15), 0.6, 0.3,
                            linewidth=1, edgecolor=color, facecolor=color, alpha=0.9
                        )
                    ax.add_patch(pkt_rect)

                # Kuyruk ve bloke bilgisi
                blocked_feeders = []
                for f_data in snapshot['feeders']:
                    if f_data.get('is_blocked', False):
                        blocked_feeders.append(f_data['id'][-1])

                if blocked_feeders:
                    ax.text(max_x - 1, max_y - 1,
                           f"Bekliyor: {','.join(blocked_feeders)}",
                           fontsize=7, color='#FFD700', ha='right')

                ax.set_xlim(min_x, max_x)
                ax.set_ylim(min_y, max_y)
                ax.set_aspect('equal')
                ax.set_title(f't={snapshot["time"]:.0f}s | {len(snapshot["conveyor_line"]["packets"])} pkt',
                            fontsize=8, color='white')
                ax.axis('off')
            else:
                ax.axis('off')

        snapshot_interval = self.config['simulation']['snapshot_interval']
        plt.suptitle(f'Snapshot Frames ({snapshot_interval}s aralik) - Sari border = Feeder bekliyor',
                    fontsize=14, fontweight='bold', color='white')
        plt.tight_layout()
        output_path = self.output_dir / 'snapshot_frames.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"📊 Snapshot frame'leri kaydedildi: {output_path}")
        plt.show()

    def visualize_executive_dashboard(self):
        """Yönetici özet dashboard'u - Tek bakışta tüm KPI'lar."""
        fig = plt.figure(figsize=(18, 12))
        fig.patch.set_facecolor('#1a1a1a')

        gs = fig.add_gridspec(3, 4, hspace=0.35, wspace=0.3,
                              left=0.05, right=0.95, top=0.90, bottom=0.08)

        sim_cfg = self.config['simulation']
        duration = sim_cfg['duration']

        # KPI 1: Toplam İşlenen Paket
        ax_kpi1 = fig.add_subplot(gs[0, 0])
        ax_kpi1.set_facecolor('#2d2d2d')
        total_processed = self.conveyor_line.total_packets_processed
        ax_kpi1.text(0.5, 0.65, f"{total_processed}", fontsize=48, fontweight='bold',
                    color='#2ECC71', ha='center', va='center', transform=ax_kpi1.transAxes)
        ax_kpi1.text(0.5, 0.25, "Islenen Paket", fontsize=14, color='white',
                    ha='center', va='center', transform=ax_kpi1.transAxes)
        ax_kpi1.text(0.5, 0.08, f"({total_processed/duration*60:.1f} paket/dk)", fontsize=10,
                    color='#888888', ha='center', va='center', transform=ax_kpi1.transAxes)
        ax_kpi1.axis('off')

        # KPI 2: Sistem Verimliliği
        ax_kpi2 = fig.add_subplot(gs[0, 1])
        ax_kpi2.set_facecolor('#2d2d2d')
        total_produced = sum(f.total_produced for f in self.feeders)
        total_transferred = sum(f.total_transferred for f in self.feeders)
        system_efficiency = (total_transferred / total_produced * 100) if total_produced > 0 else 0
        eff_color = '#2ECC71' if system_efficiency >= 80 else '#F39C12' if system_efficiency >= 50 else '#E74C3C'
        ax_kpi2.text(0.5, 0.65, f"%{system_efficiency:.0f}", fontsize=48, fontweight='bold',
                    color=eff_color, ha='center', va='center', transform=ax_kpi2.transAxes)
        ax_kpi2.text(0.5, 0.25, "Sistem Verimliligi", fontsize=14, color='white',
                    ha='center', va='center', transform=ax_kpi2.transAxes)
        ax_kpi2.text(0.5, 0.08, f"({total_transferred}/{total_produced} paket)", fontsize=10,
                    color='#888888', ha='center', va='center', transform=ax_kpi2.transAxes)
        ax_kpi2.axis('off')

        # KPI 3: Ortalama Doluluk
        ax_kpi3 = fig.add_subplot(gs[0, 2])
        ax_kpi3.set_facecolor('#2d2d2d')
        utilizations = [s['conveyor_line']['utilization'] for s in self.snapshots]
        avg_utilization = sum(utilizations) / len(utilizations) * 100 if utilizations else 0
        util_color = '#E74C3C' if avg_utilization >= 90 else '#F39C12' if avg_utilization >= 70 else '#2ECC71'
        ax_kpi3.text(0.5, 0.65, f"%{avg_utilization:.0f}", fontsize=48, fontweight='bold',
                    color=util_color, ha='center', va='center', transform=ax_kpi3.transAxes)
        ax_kpi3.text(0.5, 0.25, "Ort. Doluluk", fontsize=14, color='white',
                    ha='center', va='center', transform=ax_kpi3.transAxes)
        status = "KRITIK" if avg_utilization >= 90 else "YUKSEK" if avg_utilization >= 70 else "NORMAL"
        ax_kpi3.text(0.5, 0.08, status, fontsize=10, color=util_color,
                    ha='center', va='center', transform=ax_kpi3.transAxes)
        ax_kpi3.axis('off')

        # KPI 4: Darboğaz Durumu
        ax_kpi4 = fig.add_subplot(gs[0, 3])
        ax_kpi4.set_facecolor('#2d2d2d')
        bottleneck_feeder = max(self.feeders, key=lambda f: f.get_current_blocked_time())
        bottleneck_time = bottleneck_feeder.get_current_blocked_time()
        bottleneck_pct = (bottleneck_time / duration * 100) if duration > 0 else 0
        bn_color = '#E74C3C' if bottleneck_pct >= 50 else '#F39C12' if bottleneck_pct >= 20 else '#2ECC71'
        ax_kpi4.text(0.5, 0.65, f"%{bottleneck_pct:.0f}", fontsize=48, fontweight='bold',
                    color=bn_color, ha='center', va='center', transform=ax_kpi4.transAxes)
        ax_kpi4.text(0.5, 0.25, "Darbogaz Orani", fontsize=14, color='white',
                    ha='center', va='center', transform=ax_kpi4.transAxes)
        ax_kpi4.text(0.5, 0.08, f"({bottleneck_feeder.id})", fontsize=10,
                    color='#888888', ha='center', va='center', transform=ax_kpi4.transAxes)
        ax_kpi4.axis('off')

        # Feeder Performans Bar Chart
        ax_perf = fig.add_subplot(gs[1, 0:2])
        ax_perf.set_facecolor('#1a1a1a')

        feeder_names = [f.id.replace('FEEDER_', '') for f in self.feeders]
        efficiencies = [f.get_utilization_rate() * 100 for f in self.feeders]
        colors = [self.FEEDER_COLORS.get(f.id, '#FFFFFF') for f in self.feeders]

        bars = ax_perf.barh(feeder_names, efficiencies, color=colors, alpha=0.8, height=0.6)

        for bar, eff in zip(bars, efficiencies):
            width = bar.get_width()
            label_color = 'white' if width > 50 else '#CCCCCC'
            ax_perf.text(width - 5 if width > 50 else width + 2, bar.get_y() + bar.get_height()/2,
                        f'%{eff:.0f}', ha='right' if width > 50 else 'left', va='center',
                        fontsize=14, fontweight='bold', color=label_color)

        ax_perf.set_xlim(0, 105)
        ax_perf.set_xlabel('Verimlilik (%)', fontsize=11, color='white')
        ax_perf.set_title('Feeder Performansi', fontsize=13, fontweight='bold', color='white', pad=10)
        ax_perf.axvline(x=80, color='#2ECC71', linestyle='--', alpha=0.5)
        ax_perf.tick_params(colors='white')
        ax_perf.spines['top'].set_visible(False)
        ax_perf.spines['right'].set_visible(False)
        ax_perf.spines['bottom'].set_color('#444444')
        ax_perf.spines['left'].set_color('#444444')

        # Doluluk Trendi
        ax_trend = fig.add_subplot(gs[1, 2:4])
        ax_trend.set_facecolor('#1a1a1a')

        times = [s['time'] for s in self.snapshots]
        util_values = [s['conveyor_line']['utilization'] * 100 for s in self.snapshots]

        ax_trend.fill_between(times, util_values, alpha=0.3, color='#9B59B6')
        ax_trend.plot(times, util_values, color='#9B59B6', linewidth=2)
        ax_trend.axhline(y=80, color='#E74C3C', linestyle='--', linewidth=2, alpha=0.7)

        ax_trend.set_xlabel('Zaman (saniye)', fontsize=11, color='white')
        ax_trend.set_ylabel('Doluluk (%)', fontsize=11, color='white')
        ax_trend.set_title('Konveyor Doluluk Trendi', fontsize=13, fontweight='bold', color='white', pad=10)
        ax_trend.set_ylim(0, 120)
        ax_trend.tick_params(colors='white')
        ax_trend.spines['top'].set_visible(False)
        ax_trend.spines['right'].set_visible(False)
        ax_trend.spines['bottom'].set_color('#444444')
        ax_trend.spines['left'].set_color('#444444')

        # Pasta Grafik - Paket Durumu
        ax_pie = fig.add_subplot(gs[2, 0:2])
        ax_pie.set_facecolor('#1a1a1a')

        total_in_queue = sum(len(f.queue) for f in self.feeders)
        on_conveyor = len(self.conveyor_line.packets_in_transit)

        pie_data = [total_processed, on_conveyor, total_in_queue]
        pie_labels = ['Tamamlanan', 'Tasimada', 'Kuyrukta']
        pie_colors = ['#2ECC71', '#3498DB', '#F39C12']

        if sum(pie_data) > 0:
            ax_pie.pie(pie_data, labels=pie_labels, colors=pie_colors,
                      autopct=lambda pct: f'{pct:.0f}%' if pct > 0 else '',
                      startangle=90, textprops={'color': 'white', 'fontsize': 11})
        ax_pie.set_title('Paket Durumu Dagilimi', fontsize=13, fontweight='bold', color='white', pad=10)

        # Sonuç Kutusu
        ax_summary = fig.add_subplot(gs[2, 2:4])
        ax_summary.set_facecolor('#2d2d2d')
        ax_summary.axis('off')

        if system_efficiency >= 80 and avg_utilization < 90:
            overall_status = "IYI"
            status_color = "#2ECC71"
        elif system_efficiency >= 50 or avg_utilization < 100:
            overall_status = "ORTA"
            status_color = "#F39C12"
        else:
            overall_status = "KRITIK"
            status_color = "#E74C3C"

        ax_summary.text(0.5, 0.7, f"SISTEM DURUMU: {overall_status}", fontsize=24, fontweight='bold',
                       color=status_color, ha='center', va='center', transform=ax_summary.transAxes)

        summary_text = f"Toplam Hat: {self.conveyor_line.total_length}m\n"
        summary_text += f"Segment Sayisi: {len(self.conveyor_line.segments)}\n"
        summary_text += f"Feeder Sayisi: {len(self.feeders)}"
        ax_summary.text(0.5, 0.35, summary_text, fontsize=12,
                       color='white', ha='center', va='center', transform=ax_summary.transAxes)

        fig.suptitle('YONETICI OZET DASHBOARD', fontsize=20, fontweight='bold', color='white', y=0.96)

        plt.tight_layout(rect=[0, 0.04, 1, 0.94])
        output_path = self.output_dir / 'executive_dashboard.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"📊 Yönetici Dashboard kaydedildi: {output_path}")
        plt.show()

    def print_snapshot_summary(self):
        """Snapshot'ların özetini yazdırır"""
        snapshot_interval = self.config['simulation']['snapshot_interval']
        print("\n" + "="*70)
        print(f"📸 SNAPSHOT ÖZETİ ({snapshot_interval} saniyelik aralıklar)")
        print("="*70)

        print(f"\nToplam snapshot sayısı: {len(self.snapshots)}")
        print(f"Snapshot aralığı: {snapshot_interval} saniye")
        print(f"Toplam süre: {self.snapshots[-1]['time'] if self.snapshots else 0:.0f} saniye")


def main():
    """Ana fonksiyon"""
    config = load_config()

    # Segment bilgilerini göster
    segments_cfg = config.get('conveyor_segments', [])
    feeders_cfg = config.get('feeders', [])

    total_length = sum(s['length'] for s in segments_cfg)

    print(f"""
╔════════════════════════════════════════════════════════════════════╗
║         İTERASYON 3: MULTI-SEGMENT CONVEYOR LINE                  ║
║                                                                    ║
║  Hedef: Farklı hızlara sahip segment'lerden oluşan hat            ║
║                                                                    ║
║  Segment'ler:                                                      ║""")

    for seg in segments_cfg:
        print(f"║    • {seg['id']}: {seg['length']}m @ {seg['speed']}m/s - {seg.get('description', '')}")
        print(f"║      " + " " * 50 + "║")

    print(f"""║                                                                    ║
║  Toplam Hat: {total_length}m                                              ║
║  Feeder: {len(feeders_cfg)} adet                                               ║
║  Simülasyon: {config['simulation']['duration']}s                                       ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    # Simülasyon
    sim = MultiSegmentSimulation(config)
    sim.setup()
    sim.run()
    sim.print_statistics()
    sim.print_snapshot_summary()

    # Görselleştirmeler
    print("\n📊 Görselleştirmeler oluşturuluyor...")
    sim.visualize_executive_dashboard()
    sim.visualize_system_layout()
    sim.visualize_speed_impact()
    sim.visualize_snapshot_frames()

    print("\n▶️  Canlı simülasyon başlatılıyor...")
    sim.visualize_live(interval_ms=400)

    print("\n✅ Simülasyon tamamlandı!")
    print(f"📁 Çıktılar: {sim.output_dir}")
    print("\nOluşturulan dosyalar:")
    print("  - executive_dashboard.png")
    print("  - multisegment_layout.png")
    print("  - multisegment_analysis.png")
    print("  - snapshot_frames.png")


if __name__ == "__main__":
    main()
