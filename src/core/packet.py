from typing import Optional
from dataclasses import dataclass, field
@dataclass
class Packet:
    id:str 
    length:float = 0.3 # metre
    width:float = 0.3  # metre
    height:float = 0.3 # metre

    position: float = 0.0
    created_at: float = 0.0
    entered_conveyor_at:float = 0.0
    current_conveyor: Optional[str] = None 
    source_feeder: Optional[str] = None
    destination: Optional[str] = None

    total_wait_time: float = 0.0
    wait_events:list = field(default_factory=list)
    path_history: list = field(default_factory=list)


    def __post_init__(self):
        if not self.id:
            raise ValueError("Packet ID can't be empty")
        
    def enter_conveyor(self, conveyor_id:str, time: float):
        self.current_conveyor = conveyor_id
        self.entered_conveyor_at = time
        self.position = 0.0
        self.path_history.append(
            {
                "conveyor":conveyor_id,
                "entered_at":time
            }
        )

    def start_waiting(self, location:str, time:float):
        self.wait_events.append(
            {
                "location":location,
                "start_time": time,
                "end_time": None
            }
        )

    
    def stop_waiting(self, time:float):
        if self.wait_events and self.wait_events[-1]["end_time"]:
            self.wait_events[-1]["end_time"] = time
            wait_duration = time - self.wait_events[-1]["start_time"]
            self.total_wait_time += wait_duration

    
    def get_total_travel_time(self, current_time:float):
        """
            Toplam seyahat süresini döndürür

            Returns:
                Toplam süre (saniye)
        """

        return current_time - self.created_at

    def get_utilization_rate(self, current_time:float):

        """
            Bekleme/hareket oranını hesaplar.
            Returns:
            0.0 - 1.0 arası değer ( 1 hiç bekleme yok )
        """

        total_time = self.get_total_travel_time

    
    def __repr__(self):
        return (f"Packet(id={self.id}, position={self.position}m,conveyor={self.current_conveyor})")
    
    def to_dict(self):
        return{
            "id": self.id,
            "position": self.position,
            "current_conveyor": self.current_conveyor,
            "created_at": self.created_at,
            "total_wait_time": self.total_wait_time,
            "source_feeder": self.source_feeder

        }