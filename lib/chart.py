from pyqtgraph import PlotWidget
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QThread
from PySide6.QtGui import QFont
from typing import Union

from lib.logger import logger


class Chart:
    def __init__(self, chart: PlotWidget, display: QLabel, unit: str = ''):
        self.chart = chart
        self.display = display
        self.unit = unit
        self.formatGraph()

    def formatGraph(self):
        # graph.setTitle(title)
        self.chart.setLabel('left', f'Value ({self.unit})')
        self.chart.setLabel('bottom', 'Packet Count')
        self.chart.getAxis(
            'bottom').setTickFont(QFont("Consolas"))
        self.chart.getAxis(
            'left').setTickFont(QFont("Consolas"))

    def plot(self, x: list, y: Union[list, tuple]):
        self.chart.clear()
        if type(y) is tuple:
            try:
                self.display.setText(
                    f'{y[0][-1]}, {y[1][-1]}, {y[2][-1]} {self.unit}')
            except Exception as e:
                print(f'Error setting chart text display: {e}')
            self.chart.plot(**{'x': x[-50:-1], 'y': y[0][-50:-1],
                               'symbol': 'o', 'symbolSize': 6, 'symbolPen': 'r', 'pen': 'r'})
            self.chart.plot(**{'x': x[-50:-1], 'y': y[1][-50:-1],
                               'symbol': 'o', 'symbolSize': 6, 'symbolPen': 'g', 'pen': 'g'})
            self.chart.plot(**{'x': x[-50:-1], 'y': y[2][-50:-1],
                               'symbol': 'o', 'symbolSize': 6, 'symbolPen': 'c', 'pen': 'c'})
        else:
            try:
                self.display.setText(f'{y[-1]} {self.unit}')
            except Exception as e:
                print(f'Error setting chart text display: {e}')
            self.chart.plot(**{'x': x[-50:-1], 'y': y[-50:-1],
                               'symbol': 'o', 'symbolSize': 6})
        return
        plottingThread = PlottingThread(
            self.chart, self.display, x, y, self.unit)
        plottingThread.start()

    def clear(self):
        self.chart.clear()
        self.display.setText('N/A')


class PlottingThread(QThread):
    def __init__(self, chart: PlotWidget, display: QLabel, x: list, y: list, unit: str):
        self.chart = chart
        self.x = x
        self.y = y
        self.display = display
        self.unit = unit
        self._isRunning = True
        QThread.__init__(self)

    def __del__(self):
        self.wait()

    def run(self):
        logger.info('Plotting thread started')

    def stop(self):
        self._isRunning = False
        self.terminate()
