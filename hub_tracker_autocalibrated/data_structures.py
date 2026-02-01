#!/usr/bin/env python3
"""
Модуль data_structures.py
Содержит базовые структуры данных для VR трекинга
"""
from dataclasses import dataclass, field
from typing import List, Optional
import time

@dataclass
class ControllerData:
    """
    Хранит данные контроллера в реальном времени
    
    Атрибуты:
      controller_id: 0=LEFT, 1=RIGHT, 2=HMD
      position: [X, Y, Z] калиброванная позиция в метрах
      quaternion: [W, X, Y, Z] вращение
      aruco_position: сырая позиция от маркера до калибровки
      last_update: время последнего обновления
    """
    controller_id: int
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    quaternion: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    gyro: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    buttons: int = 0
    trigger: int = 0
    packet_number: int = 0
    last_update: float = 0.0
    source: str = "unknown"
    aruco_position: Optional[List[float]] = None
    aruco_quaternion: Optional[List[float]] = None
    aruco_last_update: float = 0.0
    gyro_quaternion: Optional[List[float]] = None
    gyro_last_update: float = 0.0
    gyro_drift_correction: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    
    def is_active(self, timeout: float = 1.0) -> bool:
        """Возвращает True если контроллер получал данные в течение timeout секунд"""
        return (time.time() - self.last_update) < timeout
    
    def has_aruco(self, timeout: float = 0.5) -> bool:
        """Возвращает True если данные ArUco маркера свежие"""
        return self.aruco_position is not None and (time.time() - self.aruco_last_update) < timeout
    
    def has_gyro(self, timeout: float = 0.5) -> bool:
        """Возвращает True если данные гироскопа свежие"""
        return self.gyro_quaternion is not None and (time.time() - self.gyro_last_update) < timeout


@dataclass
class CalibrationData:
    """
    Хранит все параметры калибровки для одного контроллера
    
    Система на основе OFFSET:
      Финальная позиция = (raw_position - reference_position) + offset
                         × scale
                         с применением инверсии осей
    
    Такой подход позволяет маркеру двигаться в реальном мире, при этом
    позиция контроллера автоматически пересчитывается относительно движения маркера
    """
    # Параметры калибровки позиции
    position_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    """Смещение добавляемое к позиции контроллера в метрах [X, Y, Z]"""
    
    position_scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    """Масштаб для каждой оси (1.0 = без масштаба, 0.8 = 80%, 1.2 = 120%)"""
    
    axis_invert: List[bool] = field(default_factory=lambda: [False, False, False])
    """Инверсия направления оси [X, Y, Z] если система координат противоположна"""
    
    rotation_invert: List[bool] = field(default_factory=lambda: [False, False, False])
    """
    Per-axis inversion of the ORIENTATION quaternion [X, Y, Z].
    
    Why this exists:
      The phone camera can be mounted facing the user OR away from the user.
      When the camera flips, the ArUco frame flips with it — rotations that
      were clockwise become counter-clockwise in certain axes.
      Auto-calibration fixes POSITION via rotation_offset_quat, but the
      orientation conjugation  (rot * relative * conj(rot))  preserves the
      handedness of each rotation axis.  If the camera is on the "wrong" side,
      some axes come out inverted.
    
    How it works:
      After the world-frame quaternion [W, X, Y, Z] is computed, each
      component X / Y / Z whose flag is True gets its sign flipped.
      Negating quaternion component X reverses the rotation around the X-axis,
      and likewise for Y and Z.  W is never touched.
    
    Typical scenario:
      Marker lying flat on a table, phone looking DOWN at it.
      CW rotation of the marker → ArUco reports CW around camera-Z.
      If camera-Z maps to world +Z the VR hand spins CW  — correct.
      If the phone is flipped (camera looks UP), camera-Z maps to world −Z,
      so the VR hand spins CCW  — wrong.  Enabling rotation_invert[2] (Z)
      flips it back.
    """
    
    rotation_offset_quat: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    """Базовое вращение сохраненное при калибровке вращения [W, X, Y, Z]"""
    
    # Референсная точка для OFFSET вычислений
    calibration_reference_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    """Позиция маркера в момент калибровки - используется как базовая для offset вычислений"""
    
    calibration_reference_rotation: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    """Вращение маркера в момент калибровки"""
    
    # Компенсация дрейфа гироскопа (для будущей fusion)
    gyro_drift_yaw: float = 0.0
    gyro_drift_pitch: float = 0.0
    gyro_drift_roll: float = 0.0
    drift_history_aruco: List[List[float]] = field(default_factory=list)
    drift_history_gyro: List[List[float]] = field(default_factory=list)
    drift_history_size: int = 100