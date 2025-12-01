import simpy
from typing import Optional, Tuple, List
from .packet import Packet
from simpy import Environment
class Conveyor:
    def __init__(self,
                 env: Environment,
                 id: str,
                 length: float, # Meter
                 speed:float = 0.5, # Meter/second
                 start_position: Tuple[float,float] = (0,0),
                 end_position: Optional[Tuple[float,float]] = None,
                 min_gap: float = 0.5,  # Paketler arası minimum mesafe
                 default_packet_length: float = 0.3  # Varsayılan paket uzunluğu
                ):

        self.env = env
        self.id = id
        self.length = length
        self.speed = speed
        self.start_pos = start_position
        self.min_gap = min_gap
        self.default_packet_length = default_packet_length

        if end_position is None:
            self.end_pos = (self.start_pos[0] + length , self.start_pos[1] + length)
        else:
            self.end_pos = end_position


        self.packets: List[Packet] = []

        self.capacity = self._calculate_belt_capacity(self.default_packet_length, self.min_gap)

        self.total_packets_processed = 0
        self.total_packets_on_process = 0
        self.utilization_history = []

    
    
        
    def _calculate_belt_capacity(self, packet_length:float=0.5, min_gap:float=0.5)  ->  int:
        """
            Konveyörün taşıyabileceği maksimum paket kapasitesini hesaplar.
            
            Args: 
                min_gap: iki paket ara minimum mesafe (metre)
                packet_length: bir paketin uzunluğu (metre)

            
        """

        totalArea_per_packet = packet_length + min_gap
        return int(self.length / totalArea_per_packet)
    

    def has_space_at(self, entry_position: float, packet_length: float = 0.5, min_gap: float = 0.5) -> bool:
        """
        Belirli bir pozisyonda paket için yer var mı kontrol eder.

        Args:
            entry_position: Paketin gireceği pozisyon (konveyör üzerinde metre)
            packet_length: Paket uzunluğu (metre)
            min_gap: Minimum paket arası mesafe (metre)

        Returns:
            True eğer o pozisyonda yer varsa
        """
        if not self.packets:
            return True

        req_space = packet_length + min_gap

        # entry_position etrafında yeterli boşluk var mı kontrol et
        for p in self.packets:
            # Paket pozisyonu ile giriş noktası arasındaki mesafe
            distance = abs(p.position - entry_position)
            if distance < req_space:
                return False

        return True

    def has_space(self, packet_length: float, min_gap: float = 0.5) -> bool:
        """
        Konveyör başında (pozisyon 0) yer var mı kontrol eder.
        Geriye uyumluluk için korundu.
        """
        return self.has_space_at(0.0, packet_length, min_gap)
    
    def accept_packet(self, packet: Packet, entry_position: float = 0.0) -> bool:
        """
        Paketi konveyöre kabul eder.

        Args:
            packet: Eklenecek paket
            entry_position: Paketin giriş pozisyonu (varsayılan: 0, konveyör başı)

        Returns:
            True eğer paket kabul edildiyse
        """
        # Giriş pozisyonunu konveyör sınırları içinde tut
        entry_position = max(0.0, min(entry_position, self.length))

        if not self.has_space_at(entry_position, packet.length, self.min_gap):
            return False

        packet.enter_conveyor(self.id, self.env.now, entry_position)

        self.packets.append(packet)
        self.total_packets_on_process += 1

        self.env.process(self._move_packet(packet))

        return True

    def _move_packet(self, packet: Packet):
        """
        Paketi konveyörde hareket ettir.
        Paketin mevcut pozisyonundan konveyör sonuna kadar taşır.
        """
        # Kalan mesafeyi hesapla (paketin mevcut pozisyonundan sona kadar)
        remaining_distance = self.length - packet.position

        if remaining_distance <= 0:
            self._packet_reached_end(packet)
            return

        travel_time = remaining_distance / self.speed

        # Animasyon için adım sayısını kalan mesafeye orantılı yap
        steps = max(10, int(100 * (remaining_distance / self.length)))
        step_time = travel_time / steps
        step_distance = remaining_distance / steps

        for step in range(steps):
            yield self.env.timeout(step_time)
            packet.position += step_distance

            if packet.position >= self.length:
                packet.position = self.length
                break

        self._packet_reached_end(packet)


    def _packet_reached_end(self, packet:Packet):
        """
            Paket konveyör sonunda ise çağrılır
            Args:
                packet: sona ulaşan packet
        """

        if packet in self.packets:
            self.packets.remove(packet)
            self.total_packets_processed += 1

        
    def get_utilization(self) -> float:
        """
            Mevcut kullanım oranını hesaplar

            Return 0-1(1 tam dolu)
        """

        return len(self.packets) / self.capacity if self.capacity > 0 else 0.0
    

    def record_utilization(self):
        """
            Mevcut kullanım oranını kaydet
            
        """

        self.utilization_history.append({
            'time': self.env.now,
            'utilization': self.get_utilization(),
            'packet_count': len(self.packets)
        })


    def get_packet_position(self) -> List[Tuple[str,float]]:
        """
            Tüm paketlerin pozisyonlarını döndürür ( graph için )

        """
        return [(p.id, p.position) for p in self.packets]
    

    def get_world_position(self,local_position: float) -> Tuple[float, float]:
        """
        Konveyör üzerindeki lokal pozisyonu dünya koordinatına çevirir.
        
        Args:
            local_position: Konveyör başından itibaren mesafe (0-length)
            
        Returns:
            (x, y) dünya koordinatı
        """
        ratio = local_position / self.length
        x = self.start_pos[0] + ratio * (self.end_pos[0] - self.start_pos[0])
        y = self.start_pos[1] + ratio * (self.end_pos[1] - self.start_pos[1])
        return (x, y)
    
    def __repr__(self) -> str:
        return (f"Conveyor(id={self.id}, length={self.length}m, "
                f"packets={len(self.packets)}/{self.capacity})")
    
    def to_dict(self) -> dict:
        """Konveyörü dictionary'ye çevirir"""
        return {
            'id': self.id,
            'length': self.length,
            'speed': self.speed,
            'capacity': self.capacity,
            'current_packets': len(self.packets),
            'utilization': self.get_utilization(),
            'total_processed': self.total_packets_processed
        }