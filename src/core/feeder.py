"""
Feeder Line: Ana konveyöre paket besleyen kaynak hatlar
"""

import simpy
from typing import Optional, Tuple, List, Union
from .packet import Packet
from .conveyor import Conveyor
from .conveyor_line import ConveyorLine


class FeederLine:
    """
    Feeder Line - Paket üreten ve ana konveyöre besleyen hat.

    Özellikler:
    - Belirli frekansta paket üretir
    - Ana konveyörde yer yoksa bekler (bloke olur)
    - Ürettiği paketleri kuyruğa alır
    - Hem tek Conveyor hem de ConveyorLine ile çalışabilir
    """

    def __init__(self,
                 env: simpy.Environment,
                 id: str,
                 target_conveyor: Union[Conveyor, ConveyorLine],
                 production_rate: float = 0.2,  # paket/saniye (varsayılan: her 5 saniyede 1)
                 entry_position: float = 0.0,  # Global giriş pozisyonu
                 max_queue_size: int = 100,
                 connection_point: Tuple[float, float] = None  # Geriye uyumluluk için
                ):
        """
        Args:
            env: SimPy environment
            id: Feeder ID (örn: "FEEDER_001")
            target_conveyor: Hedef ana konveyör veya konveyör hattı
            production_rate: Üretim hızı (paket/saniye)
            entry_position: Hat üzerindeki global giriş pozisyonu (metre)
            max_queue_size: Maksimum kuyruk boyutu
            connection_point: (Eski API) Ana konveyöre bağlantı noktası (x, y)
        """
        self.env = env
        self.id = id
        self.target_conveyor = target_conveyor
        self.production_rate = production_rate
        self.max_queue_size = max_queue_size

        # Giriş pozisyonunu belirle
        if connection_point is not None:
            # Geriye uyumluluk: eski API kullanılmış
            self.entry_position = connection_point[0]
            self.connection_point = connection_point
        else:
            self.entry_position = entry_position
            self.connection_point = (entry_position, 0)

        # İstatistikler
        self.queue: List[Packet] = []  # Bekleyen paketler
        self.total_produced = 0
        self.total_transferred = 0
        self.total_blocked_time = 0.0
        self.is_blocked = False
        self.last_block_time = 0.0
        
        # Performans metrikleri
        self.queue_length_history = []
        self.block_events = []
        
    def start_production(self):
        """
        Paket üretim sürecini başlatır.
        Sürekli olarak belirlenen frekansta paket üretir.
        """
        packet_counter = 0
        
        while True:
            # Yeni paket üret
            packet_counter += 1
            packet = Packet(
                id=f"{self.id}_PKT_{packet_counter:03d}",
                source_feeder=self.id,
                created_at=self.env.now
            )
            
            self.total_produced += 1
            
            # Kuyruğa ekle
            if len(self.queue) < self.max_queue_size:
                self.queue.append(packet)
                print(f"📦 t={self.env.now:.1f}s: {self.id} → {packet.id} üretildi (kuyruk: {len(self.queue)})")
            else:
                print(f"⚠️  t={self.env.now:.1f}s: {self.id} → Kuyruk dolu! {packet.id} atıldı")
            
            # Bir sonraki üretim için bekle
            production_interval = 1.0 / self.production_rate
            yield self.env.timeout(production_interval)
    
    def transfer_process(self):
        """
        Kuyruktaki paketleri ana konveyöre aktarmayı dener.
        Sürekli kontrol eder ve yer olduğunda transfer eder.
        Paketler feeder'ın bağlantı noktasından konveyöre girer.
        """
        while True:
            if self.queue:
                packet = self.queue[0]  # İlk pakete bak (FIFO)

                # Ana konveyöre aktarmayı dene (feeder'ın giriş pozisyonundan)
                if self.target_conveyor.accept_packet(packet, self.entry_position):
                    # Başarılı transfer
                    self.queue.pop(0)
                    self.total_transferred += 1
                    
                    # Bloke durumundan çık
                    if self.is_blocked:
                        block_duration = self.env.now - self.last_block_time
                        self.total_blocked_time += block_duration
                        self.is_blocked = False
                        print(f"✅ t={self.env.now:.1f}s: {self.id} → {packet.id} aktarıldı (bloke süresi: {block_duration:.1f}s)")
                    else:
                        print(f"✅ t={self.env.now:.1f}s: {self.id} → {packet.id} aktarıldı")
                    
                    # Paket bekleme süresini güncelle
                    if packet.wait_events:
                        packet.stop_waiting(self.env.now)
                else:
                    # Transfer başarısız - bloke durumuna geç
                    if not self.is_blocked:
                        self.is_blocked = True
                        self.last_block_time = self.env.now
                        packet.start_waiting(self.id, self.env.now)
                        self.block_events.append({
                            'time': self.env.now,
                            'queue_length': len(self.queue)
                        })
                        print(f"🚫 t={self.env.now:.1f}s: {self.id} → BLOKE! (kuyruk: {len(self.queue)})")
            
            # Kuyruk durumunu kaydet
            self.record_queue_length()
            
            # Kısa bir süre bekle (transfer denemesi aralığı)
            yield self.env.timeout(0.5)
    
    def record_queue_length(self):
        """Kuyruk uzunluğunu geçmişe kaydet"""
        self.queue_length_history.append({
            'time': self.env.now,
            'queue_length': len(self.queue),
            'is_blocked': self.is_blocked
        })
    
    def get_current_blocked_time(self) -> float:
        """
        Toplam bloke süresini hesaplar (devam eden bloke dahil).

        Returns:
            Toplam bloke süresi (saniye)
        """
        total = self.total_blocked_time
        # Eğer şu an bloke durumdaysa, devam eden süreyi de ekle
        if self.is_blocked:
            total += self.env.now - self.last_block_time
        return total

    def get_utilization_rate(self) -> float:
        """
        Feeder'ın kullanım oranını hesaplar.

        Returns:
            Aktif olma oranı (0.0-1.0)
        """
        if self.env.now == 0:
            return 1.0

        blocked_time = self.get_current_blocked_time()
        active_time = self.env.now - blocked_time
        return active_time / self.env.now
    
    def get_transfer_rate(self) -> float:
        """
        Aktarma oranını hesaplar (paket/saniye).
        
        Returns:
            Gerçekleşen transfer hızı
        """
        if self.env.now == 0:
            return 0.0
        
        return self.total_transferred / self.env.now
    
    def get_statistics(self) -> dict:
        """Detaylı istatistikler döndürür"""
        return {
            'id': self.id,
            'total_produced': self.total_produced,
            'total_transferred': self.total_transferred,
            'current_queue': len(self.queue),
            'total_blocked_time': self.get_current_blocked_time(),  # Devam eden bloke dahil
            'is_blocked': self.is_blocked,
            'utilization_rate': self.get_utilization_rate(),
            'transfer_rate': self.get_transfer_rate(),
            'block_events': len(self.block_events)
        }
    
    def __repr__(self) -> str:
        return (f"FeederLine(id={self.id}, queue={len(self.queue)}, "
                f"produced={self.total_produced}, transferred={self.total_transferred}, "
                f"blocked={self.is_blocked})")