"""
İTERASYON 1: Hello Conveyor
Tek konveyör, tek paket, basit hareket simülasyonu
"""

import simpy
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from typing import List, Tuple
import sys
from pathlib import Path

# Core sınıfları import et
sys.path.append(str(Path(__file__).parent))
from core.packet import Packet
from core.conveyor import Conveyor


class SimpleSimulation:
    """Basit konveyör simülasyonu"""
    
    def __init__(self):
        self.env = simpy.Environment()
        self.conveyor = None
        self.snapshots = []
        
    def setup(self):
        """Simülasyonu hazırla"""
        # Tek konveyör oluştur: 20 metre, 0.5 m/s hız
        self.conveyor = Conveyor(
            env=self.env,
            id="MAIN_CONVEYOR",
            length=20.0,
            speed=0.5,
            start_position=(0, 5),
            end_position=(20, 5)
        )
        
        print(f"✅ Konveyör oluşturuldu: {self.conveyor}")
        print(f"   Uzunluk: {self.conveyor.length}m")
        print(f"   Hız: {self.conveyor.speed} m/s")
        print(f"   Kapasite: {self.conveyor.capacity} paket")
        
    def add_single_packet(self):
        """Tek bir paket ekle"""
        packet = Packet(
            id="PKT_001",
            created_at=self.env.now,
            source_feeder="MANUAL"
        )
        
        success = self.conveyor.accept_packet(packet)
        if success:
            print(f"✅ Paket eklendi: {packet.id}")
        else:
            print(f"❌ Paket eklenemedi!")
            
    def snapshot_collector(self, interval: float = 2.0):
        """
        Belirli aralıklarla anlık görüntü toplar.
        
        Args:
            interval: Snapshot alma aralığı (saniye)
        """
        while True:
            # Mevcut durumu kaydet
            snapshot = {
                'time': self.env.now,
                'packets': []
            }
            
            for packet in self.conveyor.packets:
                snapshot['packets'].append({
                    'id': packet.id,
                    'position': packet.position
                })
            
            self.snapshots.append(snapshot)
            
            yield self.env.timeout(interval)
    
    def run(self, duration: float = 50.0):
        """
        Simülasyonu çalıştır.
        
        Args:
            duration: Simülasyon süresi (saniye)
        """
        print(f"\n🚀 Simülasyon başlıyor... (Süre: {duration} saniye)")
        
        # Snapshot collector'ı başlat
        self.env.process(self.snapshot_collector(interval=2.0))
        
        # Simülasyonu çalıştır
        self.env.run(until=duration)
        
        print(f"\n✅ Simülasyon tamamlandı!")
        print(f"   Toplam işlenen paket: {self.conveyor.total_packets_processed}")
        print(f"   Toplam snapshot: {len(self.snapshots)}")
        
    def visualize_final(self):
        """Son durumu görselleştirir"""
        fig, ax = plt.subplots(figsize=(14, 4))
        
        # Konveyör çiz
        conv_rect = patches.Rectangle(
            (0, 4), 
            self.conveyor.length, 
            2,
            linewidth=2, 
            edgecolor='gray', 
            facecolor='lightgray',
            label='Konveyör'
        )
        ax.add_patch(conv_rect)
        
        # Başlangıç ve bitiş işaretleri
        ax.plot(0, 5, 'go', markersize=15, label='Başlangıç')
        ax.plot(self.conveyor.length, 5, 'ro', markersize=15, label='Bitiş')
        
        # Son snapshot'taki paketleri çiz
        if self.snapshots:
            last_snapshot = self.snapshots[-1]
            for pkt_data in last_snapshot['packets']:
                pos = pkt_data['position']
                # Paket kutusu
                pkt_rect = patches.Rectangle(
                    (pos - 0.3, 4.3),
                    0.6,  # paket uzunluğu
                    1.4,
                    linewidth=1,
                    edgecolor='blue',
                    facecolor='lightblue'
                )
                ax.add_patch(pkt_rect)
                ax.text(pos, 5, pkt_data['id'], 
                       ha='center', va='center', fontsize=8)
        
        ax.set_xlim(-2, self.conveyor.length + 2)
        ax.set_ylim(0, 10)
        ax.set_aspect('equal')
        ax.set_xlabel('Pozisyon (metre)', fontsize=12)
        ax.set_title('İterasyon 1: Hello Conveyor - Son Durum', fontsize=14, fontweight='bold')
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('output/plots/iteration1_final.png', dpi=150, bbox_inches='tight')
        print("\n📊 Görselleştirme kaydedildi: output/plots/iteration1_final.png")
        plt.show()
    
    def visualize_animation_frames(self):
        """Animasyon için frame'leri oluşturur"""
        fig, axes = plt.subplots(5, 5, figsize=(18, 12))
        axes = axes.flatten()
        
        # İlk 25 snapshot'ı çiz
        for idx, snapshot in enumerate(self.snapshots[:25]):
            ax = axes[idx]
            
            # Konveyör
            conv_rect = patches.Rectangle(
                (0, 4), self.conveyor.length, 2,
                linewidth=1, edgecolor='gray', facecolor='lightgray'
            )
            ax.add_patch(conv_rect)
            
            # Paketler
            for pkt_data in snapshot['packets']:
                pos = pkt_data['position']
                pkt_rect = patches.Rectangle(
                    (pos - 0.3, 4.3), 0.6, 1.4,
                    linewidth=1, edgecolor='blue', facecolor='lightblue'
                )
                ax.add_patch(pkt_rect)
            
            ax.set_xlim(-1, self.conveyor.length + 1)
            ax.set_ylim(3, 7)
            ax.set_aspect('equal')
            ax.set_title(f't = {snapshot["time"]:.1f}s', fontsize=10)
            ax.axis('off')
        
        # Kullanılmayan subplot'ları gizle
        for idx in range(len(self.snapshots[:25]), 25):
            axes[idx].axis('off')
        
        plt.suptitle('İterasyon 1: Paket Hareketi (Frame-by-Frame)', 
                    fontsize=16, fontweight='bold')
        plt.tight_layout()
        plt.savefig('output/plots/iteration1_animation_frames.png', dpi=150, bbox_inches='tight')
        print("📊 Animasyon frame'leri kaydedildi: output/plots/iteration1_animation_frames.png")
        plt.show()
    
    def print_statistics(self):
        """İstatistikleri yazdır"""
        print("\n" + "="*60)
        print("📊 SİMÜLASYON İSTATİSTİKLERİ")
        print("="*60)
        
        print(f"\n🎯 KONVEYÖR: {self.conveyor.id}")
        print(f"   Uzunluk: {self.conveyor.length} metre")
        print(f"   Hız: {self.conveyor.speed} m/s")
        print(f"   Tahmini geçiş süresi: {self.conveyor.length / self.conveyor.speed:.1f} saniye")
        print(f"   Kapasite: {self.conveyor.capacity} paket")
        print(f"   Toplam işlenen: {self.conveyor.total_packets_processed} paket")
        
        print("\n📦 PAKET BİLGİLERİ:")
        if self.snapshots:
            first = self.snapshots[0]
            last = self.snapshots[-1]
            
            if first['packets']:
                print(f"   İlk paket ID: {first['packets'][0]['id']}")
                print(f"   Başlangıç zamanı: t={first['time']:.1f}s")
                
            if last['packets']:
                print(f"   Son pozisyon: {last['packets'][0]['position']:.2f}m")
                print(f"   Son zaman: t={last['time']:.1f}s")
            else:
                print(f"   ✅ Paket konveyörden çıktı!")
                print(f"   Çıkış zamanı: ~t={last['time']:.1f}s")
        
        print("\n" + "="*60)


def main():
    """Ana fonksiyon"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║           İTERASYON 1: HELLO CONVEYOR                         ║
║                                                                ║
║  Hedef: Tek konveyörde tek paket hareketini simüle et        ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Simülasyon oluştur
    sim = SimpleSimulation()
    
    # Hazırlık
    sim.setup()
    
    # Tek paket ekle
    sim.add_single_packet()
    
    # Çalıştır
    sim.run(duration=50.0)
    
    # İstatistikler
    sim.print_statistics()
    
    # Görselleştir
    sim.visualize_final()
    sim.visualize_animation_frames()
    
    print("\n✅ İterasyon 1 tamamlandı!")
    print("📁 Çıktılar: output/plots/ klasöründe")


if __name__ == "__main__":
    main()