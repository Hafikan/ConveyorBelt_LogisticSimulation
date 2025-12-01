"""
İTERASYON 2: Feeder Lines
2 feeder line + 1 ana konveyör simülasyonu
"""

import simpy
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from typing import List, Dict
import sys
from pathlib import Path
import tomllib

# Core sınıfları import et
sys.path.append(str(Path(__file__).parent))
from core.packet import Packet
from core.conveyor import Conveyor
from core.feeder import FeederLine


def load_config(config_path: Path = None) -> dict:
    """
    TOML config dosyasını yükler.

    Args:
        config_path: Config dosyası yolu. None ise varsayılan yol kullanılır.

    Returns:
        Config dictionary
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "simulation.toml"

    with open(config_path, "rb") as f:
        return tomllib.load(f)


class FeederSimulation:
    """Feeder line simülasyonu"""

    def __init__(self, config: dict = None):
        """
        Args:
            config: Konfigürasyon dictionary. None ise config dosyasından yüklenir.
        """
        self.config = config if config is not None else load_config()
        self.env = simpy.Environment()
        self.main_conveyor = None
        self.feeders: List[FeederLine] = []
        self.snapshots = []

        # Visualization config
        vis_cfg = self.config.get('visualization', {})

        # Feeder renkleri config'den
        self.FEEDER_COLORS = vis_cfg.get('colors', {
            'FEEDER_A': '#E74C3C',
            'FEEDER_B': '#3498DB',
            'FEEDER_C': '#2ECC71',
            'FEEDER_D': '#F39C12',
        })

        # Output ayarları
        self.output_dir = Path(__file__).parent.parent / vis_cfg.get('output_dir', 'output/plots')
        self.dpi = vis_cfg.get('dpi', 150)

        # Dark tema ayarla
        theme = vis_cfg.get('theme', 'dark')
        if theme == 'dark':
            plt.style.use('dark_background')
        
    def setup(self):
        """Simülasyonu hazırla"""
        print("🏗️  Sistem kuruluyor...")

        # Config'den ana konveyör ayarları
        conv_cfg = self.config['main_conveyor']
        self.main_conveyor = Conveyor(
            env=self.env,
            id=conv_cfg['id'],
            length=conv_cfg['length'],
            speed=conv_cfg['speed'],
            start_position=tuple(conv_cfg['start_position']),
            end_position=tuple(conv_cfg['end_position'])
        )

        print(f"✅ Ana Konveyör: {self.main_conveyor}")
        print(f"   Uzunluk: {self.main_conveyor.length}m")
        print(f"   Hız: {self.main_conveyor.speed} m/s")
        print(f"   Kapasite: {self.main_conveyor.capacity} paket")
        print(f"   Geçiş süresi: {self.main_conveyor.length / self.main_conveyor.speed:.1f}s")

        # Config'den feeder'ları oluştur
        for feeder_cfg in self.config['feeders']:
            feeder = FeederLine(
                env=self.env,
                id=feeder_cfg['id'],
                target_conveyor=self.main_conveyor,
                production_rate=feeder_cfg['production_rate'],
                connection_point=tuple(feeder_cfg['connection_point']),
                max_queue_size=feeder_cfg.get('max_queue_size', 100)
            )
            self.feeders.append(feeder)

        print(f"\n✅ Feeder Lines:")
        for feeder in self.feeders:
            print(f"   {feeder.id}:")
            print(f"      Üretim hızı: {feeder.production_rate:.3f} paket/s")
            print(f"      Üretim aralığı: {1.0/feeder.production_rate:.1f} saniye")
    
    def snapshot_collector(self):
        """Belirli aralıklarla sistem durumunu kaydet"""
        interval = self.config['simulation']['snapshot_interval']
        while True:
            snapshot = {
                'time': self.env.now,
                'main_conveyor': {
                    'packets': [
                        {
                            'id': p.id,
                            'position': p.position,
                            'source': p.source_feeder
                        } 
                        for p in self.main_conveyor.packets
                    ],
                    'utilization': self.main_conveyor.get_utilization()
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
        """
        Simülasyonu çalıştır.

        Args:
            duration: Simülasyon süresi (saniye). None ise config'den alınır.
        """
        if duration is None:
            duration = self.config['simulation']['duration']

        print(f"\n🚀 Simülasyon başlıyor... (Süre: {duration} saniye)")
        print("="*70)

        # Process'leri başlat
        self.env.process(self.snapshot_collector())
        
        # Her feeder için üretim ve transfer process'lerini başlat
        for feeder in self.feeders:
            self.env.process(feeder.start_production())
            self.env.process(feeder.transfer_process())
        
        # Simülasyonu çalıştır
        self.env.run(until=duration)
        
        print("="*70)
        print(f"\n✅ Simülasyon tamamlandı!")
    
    def print_statistics(self):
        """Detaylı istatistikleri yazdır"""
        print("\n" + "="*70)
        print("📊 SİMÜLASYON İSTATİSTİKLERİ")
        print("="*70)
        
        print(f"\n🎯 ANA KONVEYÖR: {self.main_conveyor.id}")
        print(f"   Toplam işlenen paket: {self.main_conveyor.total_packets_processed}")
        print(f"   Halen üzerinde: {len(self.main_conveyor.packets)} paket")
        print(f"   Son doluluk oranı: {self.main_conveyor.get_utilization():.2%}")
        
        print(f"\n📦 FEEDER LINES:")
        for feeder in self.feeders:
            stats = feeder.get_statistics()
            print(f"\n   {stats['id']}:")
            print(f"      Üretilen: {stats['total_produced']} paket")
            print(f"      Aktarılan: {stats['total_transferred']} paket")
            print(f"      Kuyrukta: {stats['current_queue']} paket")
            print(f"      Toplam bloke süresi: {stats['total_blocked_time']:.1f}s")
            print(f"      Kullanım oranı: {stats['utilization_rate']:.2%}")
            print(f"      Transfer hızı: {stats['transfer_rate']:.3f} paket/s")
            print(f"      Bloke olma sayısı: {stats['block_events']}")
            
            # Kayıp oranı
            if stats['total_produced'] > 0:
                loss_rate = (stats['total_produced'] - stats['total_transferred'] - stats['current_queue']) / stats['total_produced']
                if loss_rate > 0:
                    print(f"      ⚠️  Kayıp oranı: {loss_rate:.2%}")
        
        print("\n" + "="*70)
    
    def visualize_system_layout(self):
        """Sistem mimarisini göster (dark tema)"""
        fig, ax = plt.subplots(figsize=(16, 10))

        # Ana konveyör
        conv_y = 10
        conv_rect = patches.Rectangle(
            (0, conv_y - 1),
            self.main_conveyor.length,
            2,
            linewidth=2,
            edgecolor='#555555',
            facecolor='#333333',
            label='Ana Konveyör'
        )
        ax.add_patch(conv_rect)

        # Feeder lines - hepsi konveyörün altında yan yana
        for idx, feeder in enumerate(self.feeders):
            x_conn = feeder.connection_point[0]
            color = self.FEEDER_COLORS.get(feeder.id, '#FFFFFF')

            # Dikey feeder çizgisi - konveyörün altında
            feeder_line = patches.Rectangle(
                (x_conn - 0.5, 3),
                1,
                6,
                linewidth=2,
                edgecolor=color,
                facecolor=color,
                alpha=0.8
            )
            ax.add_patch(feeder_line)

            # Feeder etiketi
            ax.text(x_conn, 1.5, feeder.id,
                   ha='center', va='center',
                   fontsize=11, fontweight='bold', color=color)

        # Son snapshot'taki paketler
        if self.snapshots:
            last_snapshot = self.snapshots[-1]

            for pkt_data in last_snapshot['main_conveyor']['packets']:
                pos = pkt_data['position']

                # Renk: kaynağa göre (feeder rengi)
                source = pkt_data['source']
                color = self.FEEDER_COLORS.get(source, '#FFFFFF')

                pkt_rect = patches.Rectangle(
                    (pos - 0.3, conv_y - 0.7),
                    0.6,
                    1.4,
                    linewidth=2,
                    edgecolor=color,
                    facecolor=color,
                    alpha=0.9
                )
                ax.add_patch(pkt_rect)

            # Feeder kuyruklarını göster
            for idx, feeder_data in enumerate(last_snapshot['feeders']):
                x_conn = self.feeders[idx].connection_point[0]
                queue_len = feeder_data['queue_length']
                color = self.FEEDER_COLORS.get(self.feeders[idx].id, '#FFFFFF')

                if queue_len > 0:
                    ax.text(x_conn, 0.5,
                           f"Kuyruk: {queue_len}",
                           ha='center', va='center',
                           fontsize=9, fontweight='bold',
                           color=color)

        # Başlangıç ve bitiş
        ax.plot(0, conv_y, 'o', color='#2ECC71', markersize=15, label='Giriş')
        ax.plot(self.main_conveyor.length, conv_y, 'o', color='#E74C3C', markersize=15, label='Çıkış')

        # Akış yönü oku
        ax.annotate('', xy=(self.main_conveyor.length - 1, conv_y + 2),
                   xytext=(1, conv_y + 2),
                   arrowprops=dict(arrowstyle='->', color='white', lw=2))
        ax.text(self.main_conveyor.length / 2, conv_y + 2.5, 'Akış Yönü',
               ha='center', va='bottom', fontsize=10, color='white')

        # Sistem parametreleri bilgi kutusu
        conv_cfg = self.config['main_conveyor']
        sim_cfg = self.config['simulation']

        info_text = "SİSTEM PARAMETRELERİ\n"
        info_text += "─" * 28 + "\n\n"
        info_text += f"Ana Konveyör:\n"
        info_text += f"  Uzunluk: {conv_cfg['length']} m\n"
        info_text += f"  Hız: {conv_cfg['speed']} m/s\n"
        info_text += f"  Kapasite: {self.main_conveyor.capacity} paket\n"
        info_text += f"  Geçiş süresi: {conv_cfg['length'] / conv_cfg['speed']:.1f} s\n\n"
        info_text += f"Feeder Lines:\n"
        for feeder_cfg in self.config['feeders']:
            interval = 1.0 / feeder_cfg['production_rate']
            info_text += f"  {feeder_cfg['id']}:\n"
            info_text += f"    Üretim: {interval:.1f} s/paket\n"
            info_text += f"    Pozisyon: {feeder_cfg['connection_point'][0]} m\n"
        info_text += f"\nSimülasyon: {sim_cfg['duration']} s"

        # Bilgi kutusunu sağ üst köşeye yerleştir
        ax.text(0.98, 0.98, info_text,
               transform=ax.transAxes,
               fontsize=9, fontfamily='monospace', color='white',
               verticalalignment='top', horizontalalignment='right',
               bbox=dict(boxstyle='round,pad=0.5', facecolor='#222222',
                        edgecolor='#555555', alpha=0.9))

        ax.set_xlim(-2, self.main_conveyor.length + 2)
        ax.set_ylim(-1, 15)
        ax.set_aspect('equal')
        ax.set_xlabel('Pozisyon (metre)', fontsize=12, fontweight='bold', color='white')
        ax.set_title(f'Feeder Lines - Sistem Yapısı (t={self.snapshots[-1]["time"]:.1f}s)',
                    fontsize=14, fontweight='bold', color='white')
        ax.legend(loc='upper left', fontsize=10, facecolor='#222222', edgecolor='#555555')
        ax.grid(True, alpha=0.2, color='#555555')
        ax.set_facecolor('#1a1a1a')
        fig.patch.set_facecolor('#1a1a1a')

        plt.tight_layout()
        output_path = self.output_dir / 'iteration2_system_layout.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"\n📊 Sistem düzeni kaydedildi: {output_path}")
        plt.show()
    
    def visualize_statistics(self):
        """Tüm istatistik grafiklerini tek bir dosyada göster (dark tema)"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.patch.set_facecolor('#1a1a1a')

        # 1. Feeder kuyruk zaman çizgisi (sol üst)
        ax1 = axes[0, 0]
        ax1.set_facecolor('#1a1a1a')
        for feeder in self.feeders:
            color = self.FEEDER_COLORS.get(feeder.id, '#FFFFFF')
            if feeder.queue_length_history:
                times = [h['time'] for h in feeder.queue_length_history]
                queue_lengths = [h['queue_length'] for h in feeder.queue_length_history]
                is_blocked = [h['is_blocked'] for h in feeder.queue_length_history]

                ax1.plot(times, queue_lengths, color=color, linewidth=2, label=feeder.id)
                ax1.fill_between(times, queue_lengths, alpha=0.2, color=color)

                # Bloke noktaları
                blocked_times = [t for t, b in zip(times, is_blocked) if b]
                blocked_queues = [q for q, b in zip(queue_lengths, is_blocked) if b]
                if blocked_times:
                    ax1.scatter(blocked_times, blocked_queues,
                              color='#E74C3C', s=30, alpha=0.8, zorder=5, marker='x')

        ax1.set_xlabel('Zaman (saniye)', fontsize=11, color='white')
        ax1.set_ylabel('Kuyruk Uzunluğu', fontsize=11, color='white')
        ax1.set_title('Feeder Kuyruk Durumu', fontsize=12, fontweight='bold', color='white')
        ax1.legend(loc='upper right', facecolor='#222222', edgecolor='#555555')
        ax1.grid(True, alpha=0.2, color='#555555')
        ax1.tick_params(colors='white')

        # 2. Üretim vs Aktarım (sağ üst)
        ax2 = axes[0, 1]
        ax2.set_facecolor('#1a1a1a')

        feeder_names = [f.id for f in self.feeders]
        produced = [f.total_produced for f in self.feeders]
        transferred = [f.total_transferred for f in self.feeders]
        in_queue = [len(f.queue) for f in self.feeders]

        x = np.arange(len(feeder_names))
        width = 0.25

        ax2.bar(x - width, produced, width, label='Üretilen', color='#2ECC71', alpha=0.8)
        ax2.bar(x, transferred, width, label='Aktarılan', color='#3498DB', alpha=0.8)
        ax2.bar(x + width, in_queue, width, label='Kuyrukta', color='#F39C12', alpha=0.8)

        ax2.set_xlabel('Feeder Line', fontsize=12, fontweight='bold', color='white')
        ax2.set_ylabel('Paket Sayısı', fontsize=12, fontweight='bold', color='white')
        ax2.set_title('Üretim vs Aktarım', fontsize=12, fontweight='bold', color='white')
        ax2.set_xticks(x)
        ax2.set_xticklabels(feeder_names)
        ax2.legend(facecolor='#222222', edgecolor='#555555')
        ax2.grid(True, alpha=0.2, color='#555555', axis='y')
        ax2.tick_params(colors='white')

        # Sayıları göster
        for i, (p, t, q) in enumerate(zip(produced, transferred, in_queue)):
            ax2.text(i - width, p + 0.5, str(p), ha='center', fontsize=9, fontweight='bold', color='white')
            ax2.text(i, t + 0.5, str(t), ha='center', fontsize=9, fontweight='bold', color='white')
            ax2.text(i + width, q + 0.5, str(q), ha='center', fontsize=9, fontweight='bold', color='white')

        # 3. Konveyör doluluk oranı (sol alt)
        ax3 = axes[1, 0]
        ax3.set_facecolor('#1a1a1a')

        times = [s['time'] for s in self.snapshots]
        utilizations = [s['main_conveyor']['utilization'] for s in self.snapshots]

        ax3.plot(times, utilizations, color='#9B59B6', linewidth=2, label='Doluluk Oranı')
        ax3.fill_between(times, utilizations, alpha=0.3, color='#9B59B6')
        ax3.axhline(y=0.8, color='#E74C3C', linestyle='--', linewidth=2, alpha=0.7, label='Kritik (%80)')

        ax3.set_xlabel('Zaman (saniye)', fontsize=12, fontweight='bold', color='white')
        ax3.set_ylabel('Doluluk Oranı', fontsize=12, fontweight='bold', color='white')
        ax3.set_title('Ana Konveyör Doluluk Oranı', fontsize=12, fontweight='bold', color='white')
        ax3.set_ylim(0, 1.1)
        ax3.legend(loc='upper right', facecolor='#222222', edgecolor='#555555')
        ax3.grid(True, alpha=0.2, color='#555555')
        ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.0%}'))
        ax3.tick_params(colors='white')

        # 4. Feeder performans özeti (sağ alt)
        ax4 = axes[1, 1]
        ax4.set_facecolor('#1a1a1a')
        ax4.axis('off')

        # Özet tablosu
        summary_text = "PERFORMANS ÖZETİ\n" + "=" * 40 + "\n\n"
        summary_text += f"Ana Konveyör:\n"
        summary_text += f"  İşlenen: {self.main_conveyor.total_packets_processed} paket\n"
        summary_text += f"  Doluluk: {self.main_conveyor.get_utilization():.1%}\n\n"

        for feeder in self.feeders:
            stats = feeder.get_statistics()
            color_name = feeder.id
            summary_text += f"{color_name}:\n"
            summary_text += f"  Üretilen: {stats['total_produced']}\n"
            summary_text += f"  Aktarılan: {stats['total_transferred']}\n"
            summary_text += f"  Bloke süresi: {stats['total_blocked_time']:.1f}s\n"
            summary_text += f"  Verimlilik: {stats['utilization_rate']:.1%}\n\n"

        ax4.text(0.1, 0.9, summary_text, transform=ax4.transAxes,
                fontsize=11, fontfamily='monospace', color='white',
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='#222222', edgecolor='#555555', alpha=0.9))

        plt.tight_layout()
        output_path = self.output_dir / 'iteration2_statistics.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"📊 İstatistik grafikleri kaydedildi: {output_path}")
        plt.show()

    def visualize_snapshot_timeline(self):
        """Paket pozisyonlarını zaman içinde gösterir (dark tema)"""
        fig, ax = plt.subplots(figsize=(16, 8))
        fig.patch.set_facecolor('#1a1a1a')
        ax.set_facecolor('#1a1a1a')

        # Her paket için pozisyon geçmişi topla
        packet_tracks = {}  # {packet_id: {'times': [], 'positions': [], 'source': ''}}

        for snapshot in self.snapshots:
            for pkt in snapshot['main_conveyor']['packets']:
                pkt_id = pkt['id']
                if pkt_id not in packet_tracks:
                    packet_tracks[pkt_id] = {
                        'times': [],
                        'positions': [],
                        'source': pkt['source']
                    }
                packet_tracks[pkt_id]['times'].append(snapshot['time'])
                packet_tracks[pkt_id]['positions'].append(pkt['position'])

        # Her paketi çiz (feeder renginde)
        for pkt_id, track in packet_tracks.items():
            color = self.FEEDER_COLORS.get(track['source'], '#FFFFFF')
            ax.plot(track['times'], track['positions'], '-',
                   color=color, linewidth=1.5, alpha=0.7)
            # Son noktayı işaretle
            if track['times']:
                ax.scatter(track['times'][-1], track['positions'][-1],
                          color=color, s=20, zorder=5)

        # Feeder giriş noktalarını yatay çizgilerle göster
        for feeder in self.feeders:
            color = self.FEEDER_COLORS.get(feeder.id, '#FFFFFF')
            ax.axhline(y=feeder.entry_position, color=color, linestyle='--',
                      linewidth=1, alpha=0.5, label=f'{feeder.id} giriş ({feeder.entry_position}m)')

        # Konveyör sonu
        ax.axhline(y=self.main_conveyor.length, color='#E74C3C', linestyle='-',
                  linewidth=2, alpha=0.8, label=f'Konveyör sonu ({self.main_conveyor.length}m)')

        ax.set_xlabel('Zaman (saniye)', fontsize=12, fontweight='bold', color='white')
        ax.set_ylabel('Pozisyon (metre)', fontsize=12, fontweight='bold', color='white')
        ax.set_title('Paket Pozisyonları - Zaman Çizgisi', fontsize=14, fontweight='bold', color='white')
        ax.legend(loc='upper left', fontsize=9, facecolor='#222222', edgecolor='#555555')
        ax.grid(True, alpha=0.2, color='#555555')
        ax.tick_params(colors='white')

        plt.tight_layout()
        output_path = self.output_dir / 'iteration2_timeline.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"📊 Zaman çizgisi kaydedildi: {output_path}")
        plt.show()

    def visualize_snapshot_frames(self, max_frames: int = 30):
        """Snapshot'ları frame-by-frame gösterir (dark tema)"""
        num_snapshots = min(len(self.snapshots), max_frames)
        if num_snapshots == 0:
            print("⚠️  Snapshot bulunamadı!")
            return

        # Grid boyutunu hesapla
        cols = 6
        rows = (num_snapshots + cols - 1) // cols

        fig, axes = plt.subplots(rows, cols, figsize=(20, rows * 3))
        fig.patch.set_facecolor('#1a1a1a')
        axes = axes.flatten() if num_snapshots > 1 else [axes]

        for idx in range(len(axes)):
            ax = axes[idx]
            ax.set_facecolor('#1a1a1a')

            if idx < num_snapshots:
                snapshot = self.snapshots[idx]

                # Konveyör
                conv_rect = patches.Rectangle(
                    (0, 9), self.main_conveyor.length, 2,
                    linewidth=1, edgecolor='#555555', facecolor='#333333'
                )
                ax.add_patch(conv_rect)

                # Feeder'lar
                for feeder in self.feeders:
                    color = self.FEEDER_COLORS.get(feeder.id, '#FFFFFF')
                    feeder_rect = patches.Rectangle(
                        (feeder.entry_position - 0.3, 5), 0.6, 4,
                        linewidth=1, edgecolor=color, facecolor=color, alpha=0.6
                    )
                    ax.add_patch(feeder_rect)

                # Paketler
                for pkt in snapshot['main_conveyor']['packets']:
                    color = self.FEEDER_COLORS.get(pkt['source'], '#FFFFFF')
                    pkt_rect = patches.Rectangle(
                        (pkt['position'] - 0.2, 9.2), 0.4, 1.6,
                        linewidth=1, edgecolor=color, facecolor=color, alpha=0.9
                    )
                    ax.add_patch(pkt_rect)

                # Kuyruk bilgisi
                queue_text = ""
                for f_data in snapshot['feeders']:
                    if f_data['queue_length'] > 0:
                        queue_text += f"{f_data['id'][-1]}:{f_data['queue_length']} "
                if queue_text:
                    ax.text(0.5, 4, f"Kuyruk: {queue_text}", fontsize=7, color='#F39C12')

                ax.set_xlim(-1, self.main_conveyor.length + 1)
                ax.set_ylim(3, 13)
                ax.set_title(f't={snapshot["time"]:.0f}s | {len(snapshot["main_conveyor"]["packets"])} pkt',
                            fontsize=8, color='white')
                ax.axis('off')
            else:
                ax.axis('off')

        snapshot_interval = self.config['simulation']['snapshot_interval']
        plt.suptitle(f'Snapshot Frames ({snapshot_interval} saniyelik aralıklar)',
                    fontsize=14, fontweight='bold', color='white')
        plt.tight_layout()
        output_path = self.output_dir / 'iteration2_frames.png'
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                   facecolor='#1a1a1a', edgecolor='none')
        print(f"📊 Snapshot frame'leri kaydedildi: {output_path}")
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

        print("\n{:<8} {:>10} {:>12} {:>12} {:>12}".format(
            "Zaman", "Paket#", "Doluluk", "Kuyruk(B)", "Kuyruk(C)"
        ))
        print("-" * 60)

        for snapshot in self.snapshots[::5]:  # Her 5 snapshot'tan birini göster
            time = snapshot['time']
            pkt_count = len(snapshot['main_conveyor']['packets'])
            utilization = snapshot['main_conveyor']['utilization']

            queues = {f['id']: f['queue_length'] for f in snapshot['feeders']}

            print("{:<8.0f} {:>10} {:>11.0%} {:>12} {:>12}".format(
                time, pkt_count, utilization,
                queues.get('FEEDER_B', 0),
                queues.get('FEEDER_C', 0)
            ))

        print("="*70)


def main():
    """Ana fonksiyon"""
    # Config dosyasını yükle
    config = load_config()

    # Config'den sistem bilgilerini al
    conv_cfg = config['main_conveyor']
    feeders_cfg = config['feeders']
    sim_cfg = config['simulation']

    # Feeder bilgilerini hazırla
    feeder_info = "\n".join([
        f"║    • {f['id']}: Her {1.0/f['production_rate']:.1f} saniyede 1 paket"
        + " " * (24 - len(f['id'])) + "║"
        for f in feeders_cfg
    ])

    print(f"""
╔════════════════════════════════════════════════════════════════════╗
║              İTERASYON 2: FEEDER LINES                            ║
║                                                                    ║
║  Hedef: Feeder line'lardan paket besleyen sistem                  ║
║                                                                    ║
║  Sistem (config/simulation.toml):                                  ║
{feeder_info}
║    • {conv_cfg['id']}: {conv_cfg['length']}m uzunluk, {conv_cfg['speed']} m/s hız          ║
║    • Simülasyon süresi: {sim_cfg['duration']} saniye                         ║
║                                                                    ║
║  Amaç:                                                             ║
║    ✓ Feeder'ların bloke olma durumlarını gözlemle                ║
║    ✓ Kuyruk uzunluklarını analiz et                              ║
║    ✓ Ana konveyör doluluk oranını incele                         ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    # Simülasyon oluştur (config ile)
    sim = FeederSimulation(config)

    # Kurulum
    sim.setup()

    # Çalıştır (config'den süre alınır)
    sim.run()

    # İstatistikler
    sim.print_statistics()

    # Snapshot özeti
    sim.print_snapshot_summary()

    # Görselleştirmeler
    print("\n📊 Görselleştirmeler oluşturuluyor...")
    sim.visualize_system_layout()
    sim.visualize_statistics()
    sim.visualize_snapshot_timeline()
    sim.visualize_snapshot_frames()

    print("\n✅ İterasyon 2 tamamlandı!")
    print(f"📁 Çıktılar: {sim.output_dir} klasöründe")
    print("\nOluşturulan dosyalar:")
    print("  • iteration2_system_layout.png - Sistem yapısı")
    print("  • iteration2_statistics.png - Tüm istatistikler")
    print("  • iteration2_timeline.png - Paket zaman çizgisi")
    print("  • iteration2_frames.png - Snapshot frame'leri")


if __name__ == "__main__":
    main()