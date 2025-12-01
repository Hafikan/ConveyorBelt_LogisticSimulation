"""
ConveyorLine: Birden fazla segment'ten oluşan konveyör hattı.
Her segment farklı hıza sahip olabilir.
"""

import simpy
from typing import List, Optional, Tuple, Dict
from .packet import Packet


class ConveyorSegment:
    """Tek bir konveyör segmenti"""

    def __init__(self,
                 env: simpy.Environment,
                 id: str,
                 length: float,
                 speed: float,
                 start_offset: float,  # Hat başından itibaren bu segment'in başlangıç pozisyonu
                 min_gap: float = 0.5,
                 description: str = "",
                 direction: str = "horizontal"):  # "horizontal" veya "vertical"
        self.env = env
        self.id = id
        self.length = length
        self.speed = speed
        self.start_offset = start_offset  # Global pozisyon (hat başından)
        self.end_offset = start_offset + length
        self.min_gap = min_gap
        self.description = description
        self.direction = direction  # Segment yönü

        self.packets: List[Packet] = []

    @property
    def capacity(self) -> int:
        """Segment kapasitesi"""
        packet_length = 0.3
        return int(self.length / (packet_length + self.min_gap))

    def get_local_position(self, global_position: float) -> float:
        """Global pozisyonu segment-lokal pozisyona çevirir"""
        return global_position - self.start_offset

    def get_global_position(self, local_position: float) -> float:
        """Segment-lokal pozisyonu global pozisyona çevirir"""
        return local_position + self.start_offset

    def contains_position(self, global_position: float) -> bool:
        """Bu pozisyon bu segment içinde mi?"""
        return self.start_offset <= global_position < self.end_offset

    def has_space_at(self, global_position: float, packet_length: float = 0.3) -> bool:
        """Belirtilen global pozisyonda yer var mı?"""
        req_space = packet_length + self.min_gap

        for p in self.packets:
            distance = abs(p.position - global_position)
            if distance < req_space:
                return False
        return True

    def get_utilization(self) -> float:
        """Segment doluluk oranı"""
        if self.capacity == 0:
            return 0.0
        return len(self.packets) / self.capacity

    def __repr__(self) -> str:
        return f"Segment({self.id}, {self.length}m @ {self.speed}m/s, packets={len(self.packets)})"


class ConveyorLine:
    """
    Birden fazla segment'ten oluşan konveyör hattı.
    Paketler segment'ler arasında otomatik olarak transfer edilir.
    """

    def __init__(self,
                 env: simpy.Environment,
                 id: str = "MAIN_LINE",
                 min_gap: float = 0.5,
                 default_packet_length: float = 0.3):
        self.env = env
        self.id = id
        self.min_gap = min_gap
        self.default_packet_length = default_packet_length

        self.segments: List[ConveyorSegment] = []
        self.total_length = 0.0

        # İstatistikler
        self.total_packets_processed = 0
        self.packets_in_transit: List[Packet] = []  # Tüm hattaki paketler

    def add_segment(self, id: str, length: float, speed: float,
                    description: str = "", direction: str = "horizontal"):
        """Hatta yeni segment ekler (sona eklenir)"""
        segment = ConveyorSegment(
            env=self.env,
            id=id,
            length=length,
            speed=speed,
            start_offset=self.total_length,
            min_gap=self.min_gap,
            description=description,
            direction=direction
        )
        self.segments.append(segment)
        self.total_length += length
        return segment

    def get_segment_at(self, global_position: float) -> Optional[ConveyorSegment]:
        """Belirtilen pozisyondaki segment'i döndürür"""
        for segment in self.segments:
            if segment.contains_position(global_position):
                return segment
        return None

    def get_segment_index_at(self, global_position: float) -> int:
        """Belirtilen pozisyondaki segment index'ini döndürür"""
        for i, segment in enumerate(self.segments):
            if segment.contains_position(global_position):
                return i
        return -1

    def get_speed_at(self, global_position: float) -> float:
        """Belirtilen pozisyondaki hızı döndürür"""
        segment = self.get_segment_at(global_position)
        if segment:
            return segment.speed
        return 0.0

    def get_global_entry_position(self, segment_index: int, offset: float) -> float:
        """Segment index ve offset'ten global pozisyon hesaplar"""
        if 0 <= segment_index < len(self.segments):
            return self.segments[segment_index].start_offset + offset
        return 0.0

    @property
    def capacity(self) -> int:
        """Toplam hat kapasitesi"""
        return sum(s.capacity for s in self.segments)

    @property
    def packets(self) -> List[Packet]:
        """Tüm hattaki paketler (geriye uyumluluk için)"""
        return self.packets_in_transit

    def has_space_at(self, global_position: float, packet_length: float = 0.3) -> bool:
        """Belirtilen pozisyonda yer var mı? (tüm hat genelinde kontrol)"""
        req_space = packet_length + self.min_gap

        for p in self.packets_in_transit:
            distance = abs(p.position - global_position)
            if distance < req_space:
                return False
        return True

    def accept_packet(self, packet: Packet, entry_position: float = 0.0) -> bool:
        """
        Paketi hatta kabul eder.

        Args:
            packet: Eklenecek paket
            entry_position: Global giriş pozisyonu

        Returns:
            True eğer paket kabul edildiyse
        """
        # Pozisyonu hat sınırları içinde tut
        entry_position = max(0.0, min(entry_position, self.total_length - 0.1))

        if not self.has_space_at(entry_position, packet.length):
            return False

        # Paketi başlat
        packet.position = entry_position
        packet.current_conveyor = self.id
        packet.entered_conveyor_at = self.env.now

        # Segment'e ekle
        segment = self.get_segment_at(entry_position)
        if segment:
            segment.packets.append(packet)

        self.packets_in_transit.append(packet)

        # Hareket process'ini başlat
        self.env.process(self._move_packet(packet))

        return True

    def _move_packet(self, packet: Packet):
        """
        Paketi hat boyunca hareket ettirir.
        Segment geçişlerinde hız değişir.
        """
        while packet.position < self.total_length:
            # Mevcut segment'i bul
            current_segment = self.get_segment_at(packet.position)
            if not current_segment:
                break

            # Bu segment'in sonuna kadar olan mesafe
            distance_to_segment_end = current_segment.end_offset - packet.position
            speed = current_segment.speed

            # Adım hesapla (küçük adımlarla hareket)
            step_time = 0.1  # 100ms adımlar
            step_distance = speed * step_time

            if step_distance >= distance_to_segment_end:
                # Segment sonuna ulaşacak
                travel_time = distance_to_segment_end / speed
                yield self.env.timeout(travel_time)

                # Eski segment'ten çıkar
                if packet in current_segment.packets:
                    current_segment.packets.remove(packet)

                packet.position = current_segment.end_offset

                # Yeni segment'e geç
                next_segment = self.get_segment_at(packet.position)
                if next_segment and packet.position < self.total_length:
                    next_segment.packets.append(packet)
            else:
                # Normal adım
                yield self.env.timeout(step_time)

                old_segment = current_segment
                packet.position += step_distance

                # Segment değişti mi kontrol et
                new_segment = self.get_segment_at(packet.position)
                if new_segment and new_segment != old_segment:
                    if packet in old_segment.packets:
                        old_segment.packets.remove(packet)
                    new_segment.packets.append(packet)

        # Hat sonuna ulaştı
        self._packet_reached_end(packet)

    def _packet_reached_end(self, packet: Packet):
        """Paket hat sonuna ulaştığında çağrılır"""
        # Segment'lerden çıkar
        for segment in self.segments:
            if packet in segment.packets:
                segment.packets.remove(packet)

        # Ana listeden çıkar
        if packet in self.packets_in_transit:
            self.packets_in_transit.remove(packet)

        self.total_packets_processed += 1

    def get_utilization(self) -> float:
        """Toplam hat doluluk oranı"""
        if self.capacity == 0:
            return 0.0
        return len(self.packets_in_transit) / self.capacity

    def get_segment_utilizations(self) -> Dict[str, float]:
        """Her segment'in doluluk oranını döndürür"""
        return {s.id: s.get_utilization() for s in self.segments}

    def get_statistics(self) -> dict:
        """Hat istatistikleri"""
        return {
            'id': self.id,
            'total_length': self.total_length,
            'segment_count': len(self.segments),
            'total_capacity': self.capacity,
            'packets_in_transit': len(self.packets_in_transit),
            'total_processed': self.total_packets_processed,
            'utilization': self.get_utilization(),
            'segments': [
                {
                    'id': s.id,
                    'length': s.length,
                    'speed': s.speed,
                    'packets': len(s.packets),
                    'utilization': s.get_utilization(),
                    'description': s.description
                }
                for s in self.segments
            ]
        }

    def __repr__(self) -> str:
        return (f"ConveyorLine({self.id}, {len(self.segments)} segments, "
                f"{self.total_length}m, packets={len(self.packets_in_transit)})")
