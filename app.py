from PySide6 import QtCore
from PySide6.QtCore import QThread, QTimer
from lib.port import DisconnectException
from datetime import datetime

from ui.mainwindow_ui import Ui_MainWindow
from lib.communication import TelemetryHandler, Port
from lib.logger import logger
from lib.chart import Chart
from lib.rtc import RTC
from lib.gearth import Coordinate, LoadDirectory
import settings

from PySide6 import QtWidgets
from PySide6.QtWidgets import QFileDialog, QMainWindow
import sys
import time
import pyqtgraph as pg
import os
import paho.mqtt.client as mqtt


class App(QMainWindow):

    def __init__(self):
        QMainWindow.__init__(self)

        # Initialize main window
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.show()
        # self.showMaximized()

        # Initilize MQTT
        self.mqtt_enabled = False
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = lambda client, userdata, flags, rc: print(
            "Connected to MQTT broker with result code "+str(rc))
        self.mqtt_client.on_message = lambda client, userdata, msg: print(
            msg.topic+" "+str(msg.payload))
        self.mqtt_client.username_pw_set('1022', 'Teasgote783')

        # Initialize charts
        self.c_temp_chart = Chart(
            self.ui.c_temp_chart, self.ui.c_temp_value, '°C')
        self.c_altitude_chart = Chart(
            self.ui.c_altitude_chart, self.ui.c_altitude_value, 'm')
        self.c_gps_altitude_chart = Chart(
            self.ui.c_gps_altitude_chart, self.ui.c_gps_altitude_value, 'm')
        self.c_voltage_chart = Chart(
            self.ui.c_voltage_chart, self.ui.c_voltage_value, 'V')
        self.p_temp_chart = Chart(
            self.ui.p_temp_chart, self.ui.p_temp_value, '°C')
        self.p_gyro_chart = Chart(
            self.ui.p_gyro_chart, self.ui.p_gyro_value, 'degrees/s')
        self.p_accel_chart = Chart(
            self.ui.p_accel_chart, self.ui.p_accel_value, 'm/s²')
        self.p_mag_chart = Chart(
            self.ui.p_mag_chart, self.ui.p_mag_value, 'gauss')
        self.p_ptr_err_chart = Chart(
            self.ui.p_ptr_err_chart, self.ui.p_ptr_err_value, 'degrees')
        self.p_voltage_chart = Chart(
            self.ui.p_voltage_chart, self.ui.p_voltage_value, 'V')
        self.p_altitude_chart = Chart(
            self.ui.p_altitude_chart, self.ui.p_altitude_value, 'm')

        self.reset()

        # Display available ports, if at least one available, initiate TelemetryHandler first in the list
        available_ports = Port.list()
        self.ui.port_value.addItems(available_ports)
        if available_ports:
            self.current_port = available_ports[0]
        else:
            self.current_port = None
            self.ui.port_value.setCurrentText('No Ports Available')

        self.lifecycle_thread = LifecycleThread()
        self.lifecycle_thread.lifecycleRequested.connect(self.lifecycle)
        self.telemetry_thread = TelemetryThread()
        self.telemetry_thread.received.connect(self.handleTelemetry)
        self.telemetry_thread.requestHalt.connect(self.stop_lifecycle)

        self.sim_filename = ''

        self.updateCmdPreview()

        # Connect UI components
        self.connect()

    def init_lifecycle(self):
        logger.info('Starting lifecycle ...')

        # Start timing
        self.rtc = RTC()

        logger.debug(self.current_port)
        self.telemetry = TelemetryHandler(self.current_port)

        self.lifecycle_thread.start()
        self.telemetry_thread.start()

        self.ui.telemetry_box.setEnabled(True)
        self.ui.start_button.pressed.disconnect()
        self.ui.start_button.pressed.connect(self.stop_lifecycle)
        self.ui.start_button.setText('PAUSE')

    def stop_lifecycle(self):
        logger.info('Stopping lifecycle ...')
        self.lifecycle_thread.stop()
        self.telemetry_thread.stop()

        self.telemetry.destroy()

        self.ui.telemetry_box.setEnabled(False)
        self.ui.start_button.pressed.disconnect()
        self.ui.start_button.pressed.connect(self.init_lifecycle)
        self.ui.start_button.setText('RESUME')
        self.refreshPort()

    def lifecycle(self):
        '''
        Continuous tasks go here
        '''
        self.ui.mission_time.setText(self.rtc.time_UTC())
        self.ui.elapsed_time.setText('T + '+self.rtc.time_elapsed())

        self.ui.total_pkg_value.setText(str(
            self.container_healthy_pkg+self.container_corrupted_pkg+self.payload_healthy_pkg+self.payload_corrupted_pkg))
        self.ui.total_corrupted_pkg_value.setText(
            str(self.container_corrupted_pkg+self.payload_corrupted_pkg))

    def open_sim_file(self):
        if self.sim_filename:
            os.startfile(self.sim_filename)
        else:
            self.ui.telemetry_log.append('No simulation file selected')

    def connect(self):
        '''
        Connect UI components with their respective functions.
        '''
        self.ui.actionCSVLocation.triggered.connect(
            lambda: os.startfile(('logs')))
        self.ui.actionOpen_simulation_file.triggered.connect(
            self.open_sim_file)
        self.ui.actionParachute.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'PARADEPLOY'))
        self.ui.actionPoll.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'POLL'))
        self.ui.actionPayload_On.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'TPON'))
        self.ui.actionPayload_Off.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'TPOFF'))
        self.ui.actionReset_Camera_Rotation.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'RESETCAM'))
        self.ui.actionCalibrate_Gimbal_IMU.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'CALCAM'))
        self.ui.actionForce_Polling_Payload.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'POLLON'))
        self.ui.actionUnforce_Polling_Payload.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'POLLOFF'))
        self.ui.actionRelease_Sequence.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'SEQUENCE'))
        self.ui.actionHalt_Sequence.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'HALT'))
        self.ui.actionRelease.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'RELEASE'))
        self.ui.actionBreak.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'BREAK'))
        self.ui.actionMode0.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'MODE0'))
        self.ui.actionMode1.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'MODE1'))
        self.ui.actionMode_2.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'MODE2'))
        self.ui.actionMode_3.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'MODE3'))
        self.ui.actionMode_4.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'MODE4'))
        self.ui.action0_PRELAUNCH.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'STATE0'))
        self.ui.action1_LAUNCH.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'STATE1'))
        self.ui.action2_PARADEPLOY.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'STATE2'))
        self.ui.action3_TPDEPLOY.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'STATE3'))
        self.ui.action4_RELEASED.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'STATE4'))
        self.ui.action5_LAND.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'STATE5'))
        self.ui.actionToggle_Container_Camera.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'CCAM'))
        self.ui.actionToggle_Custom_Packet.triggered.connect(
            lambda: self.telemetry.sendCommand('FORCE', 'SENDCUSTOM'))

        self.ui.actionFull_Screen.triggered.connect(self.toggleFullScreen)
        self.ui.actionExit.triggered.connect(self.close)

        # MQTT
        self.ui.actionEnable.triggered.connect(
            lambda checked: self.updateMQTT(checked))

        self.ui.port_value.currentTextChanged.connect(
            lambda text: self.selectPort(text))
        self.ui.port_refresh_button.pressed.connect(self.refreshPort)
        self.ui.sim_file_button.pressed.connect(self.selectSimFile)

        self.ui.cmd_select_box.currentTextChanged.connect(
            self.updateCmdPreview)
        self.ui.cmdSendButton_2.pressed.connect(self.sendControlCommand)

        self.ui.start_button.pressed.connect(self.init_lifecycle)
        self.ui.reset_button.pressed.connect(self.reset)

    def reset(self):
        self.container_healthy_pkg = 0
        self.container_corrupted_pkg = 0
        self.payload_healthy_pkg = 0
        self.payload_corrupted_pkg = 0

        self.c_pkg_data = []
        self.p_pkg_data = []

        self.c_temp_data = []
        self.c_altitude_data = []
        self.c_gps_altitude_data = []
        self.c_voltage_data = []
        self.c_lat_data = []
        self.c_lng_data = []
        self.p_temp_data = []
        self.p_altitude_data = []
        self.p_gyro_r_data = []
        self.p_gyro_p_data = []
        self.p_gyro_y_data = []
        self.p_accel_r_data = []
        self.p_accel_p_data = []
        self.p_accel_y_data = []
        self.p_mag_r_data = []
        self.p_mag_p_data = []
        self.p_mag_y_data = []
        self.p_ptr_err_data = []
        self.p_voltage_data = []
        self.coords = []
        self.c_temp_chart.clear()
        self.c_altitude_chart.clear()
        self.c_gps_altitude_chart.clear()
        self.c_voltage_chart.clear()
        self.p_temp_chart.clear()
        self.p_gyro_chart.clear()
        self.p_accel_chart.clear()
        self.p_mag_chart.clear()
        self.p_ptr_err_chart.clear()
        self.p_voltage_chart.clear()

        self.ui.c_state.setText('-')
        self.ui.p_state.setText('-')

        self.ui.total_pkg_value.setText('0')
        self.ui.total_corrupted_pkg_value.setText('0')
        self.ui.c_healthy_pkg_count.setText('0')
        self.ui.c_corrupted_pkg_count.setText('0')
        self.ui.p_healthy_pkg_count.setText('0')
        self.ui.p_corrupted_pkg_count.setText('0')
        self.ui.last_cmd_value.setText('-')
        self.ui.telemetry_log.clear()
        self.ui.telemetry_log.clearHistory()
        self.ui.c_battery_visual.setValue(0)
        self.ui.container_battery_percent.setText('N/A')
        self.ui.p_battery_visual.setValue(0)
        self.ui.payload_battery_percent.setText('N/A')
        self.ui.lat_value.setText('-')
        self.ui.lng_value.setText('-')
        self.ui.sats_value.setText('0')

        self.time_begin = str(RTC.date_local())+'T' + \
            RTC.time_local(False).split('.')[0]
        self.time_begin = self.time_begin.replace(':', '_')
        if not os.path.exists('logs'):
            os.mkdir('logs')
        with open('Flight_1022_C.csv', 'w') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,MODE,TP_RELEASED,ALTITUDE,TEMP,VOLTAGE,GPS_TIME,GPS_LATITUDE,GPS_LONGITUDE,GPS_ALTITUDE,GPS_SATS,SOFTWARE_STATE,CMD_ECHO\n')
        with open('Flight_1022_C_with_corrupted.csv', 'w') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,MODE,TP_RELEASED,ALTITUDE,TEMP,VOLTAGE,GPS_TIME,GPS_LATITUDE,GPS_LONGITUDE,GPS_ALTITUDE,GPS_SATS,SOFTWARE_STATE,CMD_ECHO\n')
        with open(f'logs/{self.time_begin}_Flight_1022_C.csv', 'a') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,MODE,TP_RELEASED,ALTITUDE,TEMP,VOLTAGE,GPS_TIME,GPS_LATITUDE,GPS_LONGITUDE,GPS_ALTITUDE,GPS_SATS,SOFTWARE_STATE,CMD_ECHO\n')
        with open(f'logs/{self.time_begin}_Flight_1022_C_with_corrupted.csv', 'a') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,MODE,TP_RELEASED,ALTITUDE,TEMP,VOLTAGE,GPS_TIME,GPS_LATITUDE,GPS_LONGITUDE,GPS_ALTITUDE,GPS_SATS,SOFTWARE_STATE,CMD_ECHO\n')

        with open('Flight_1022_T.csv', 'w') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,TP_ALTITUDE,TP_TEMP,TP_VOLTAGE,GYRO_R,GYRO_P,GYRO_Y,ACCEL_R,ACCEL_P,ACCEL_Y,MAG_R,MAG_P,MAG_Y,POINTING_ERROR,TP_SOFTWARE_STATE\n')
        with open('Flight_1022_T_with_corrupted.csv', 'w') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,TP_ALTITUDE,TP_TEMP,TP_VOLTAGE,GYRO_R,GYRO_P,GYRO_Y,ACCEL_R,ACCEL_P,ACCEL_Y,MAG_R,MAG_P,MAG_Y,POINTING_ERROR,TP_SOFTWARE_STATE\n')
        with open(f'logs/{self.time_begin}_Flight_1022_T.csv', 'a') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,TP_ALTITUDE,TP_TEMP,TP_VOLTAGE,GYRO_R,GYRO_P,GYRO_Y,ACCEL_R,ACCEL_P,ACCEL_Y,MAG_R,MAG_P,MAG_Y,POINTING_ERROR,TP_SOFTWARE_STATE\n')
        with open(f'logs/{self.time_begin}_Flight_1022_T_with_corrupted.csv', 'a') as file:
            file.write('TEAM_ID,MISSION_TIME,PACKET_COUNT,PACKET_TYPE,TP_ALTITUDE,TP_TEMP,TP_VOLTAGE,GYRO_R,GYRO_P,GYRO_Y,ACCEL_R,ACCEL_P,ACCEL_Y,MAG_R,MAG_P,MAG_Y,POINTING_ERROR,TP_SOFTWARE_STATE\n')

        self.dirloader = LoadDirectory(
            'neilkml', 'neilcsv', 'csv', earth_save_name=self.time_begin, folder_name='kml')

        # Initialize map
        # if not os.path.exists('kml'):
        #     os.mkdir('kml')
        # if os.path.exists('data.kml'):
        #     i = 0
        #     path = f'kml/data_{i}.kml'
        #     while(os.path.exists(path)):
        #         i += 1
        #         path = f'kml/data_{i}.kml'
        #     os.rename('data.kml', f'kml/data_{i}.kml')
        # self.map_initialized = False

    def updateMQTT(self, enable: bool):
        if enable:
            logger.info('Connecting to MQTT broker ...')
            try:
                self.mqtt_client.connect("krissada.com", 1883)
                self.mqtt_enabled = True
                logger.info('Connected to MQTT broker')
                self.ui.telemetry_log.append('Connected to MQTT broker')
            except Exception:
                logger.warning('Cannot connect to MQTT broker')
                self.ui.telemetry_log.append('❌ Cannot connect to MQTT broker')
                self.ui.actionEnable.setChecked(False)
        else:
            logger.info('Disconnected from MQTT broker')
            self.ui.telemetry_log.append('Disconnected from MQTT broker')
            self.mqtt_client.disconnect()
            self.mqtt_enabled = False

    def handleTelemetry(self, data: str):
        # Display in log widget
        if(not data or data == '\r' or data == '\n'):
            return
        # self.ui.telemetry_log.append(f'📩 {data}')
        if self.ui.autoscroll_check.isChecked():
            scrollbar = self.ui.telemetry_log.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        if data is None:
            logger.error('Received data is None')
            return
        with open('rawfilterwithouttp.csv', 'a') as f:
            f.write(data+'\n')
        pkg = data.split(',')
        # pkg[1] = datetime.utcnow().strftime('%H:%M:%S')
        # pkg[9] = datetime.utcnow().strftime('%H:%M:%S')
        if self.mqtt_enabled:
            self.mqtt_client.publish('teams/1022', data)

        # Determine package origin
        if pkg[3] == 'C':
            self.ui.telemetry_log.append(f'📩 {data}')
            # logger.info(f'[CANSAT] :{data}')
            with open('Flight_1022_C_with_corrupted.csv', 'a') as f:
                f.write(data+'\n')
            with open(f'logs/{self.time_begin}_Flight_1022_C_with_corrupted.csv', 'a') as f:
                f.write(data+'\n')
            self.latest_container_telemetry = pkg[:]
            self.updateContainer()
        elif pkg[3] == 'T':
            # PLS REMOVE THIS AFTERWARDS, THANKS :)
            self.ui.telemetry_log.append(f'📩 {data}')
            # logger.info(f'[PAYLOAD]: {data}')
            with open('Flight_1022_T_with_corrupted.csv', 'a') as f:
                f.write(data+'\n')
            with open(f'logs/{self.time_begin}_Flight_1022_T_with_corrupted.csv', 'a') as f:
                f.write(data+'\n')
            self.latest_payload_telemetry = pkg[:]
            self.updatePayload()

    def updateCmdPreview(self):
        command = self.ui.cmd_select_box.currentText()
        if hasattr(self, 'settime_preview_timer'):
            self.settime_preview_timer.stop()
        if command == 'Power ON':
            self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('CX', 'ON'))
        elif command == 'Power OFF':
            self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('CX', 'OFF'))
        elif command == 'Set Time':
            self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('ST', datetime.utcnow().strftime('%H:%M:%S')))
            self.settime_preview_timer = QTimer()
            self.settime_preview_timer.timeout.connect(lambda: self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('ST', datetime.utcnow().strftime('%H:%M:%S'))))
            self.settime_preview_timer.start(1000)

        elif command == 'SIM Enable':
            self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('SIM', 'ENABLE'))
        elif command == 'SIM Activate':
            self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('SIM', 'ACTIVATE'))
            self.startSim()
        elif command == 'SIM Disable':
            self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('SIM', 'DISABLE'))
        elif command == 'Set Apogee':
            self.ui.cmd_preview.setText(
                TelemetryHandler.previewSendCommand('SETPEAK', '10'))

    def sendControlCommand(self):
        if not hasattr(self, 'telemetry') or self.telemetry is None:
            logger.warning(
                'Unable to send command (no telemetry object found)')
            self.ui.telemetry_log.append(
                'Unable to send command (no telemetry object found)')
            return
        self.telemetry.sendRawCommand(self.ui.cmd_preview.text())
        self.ui.telemetry_log.append(f'📨 {self.ui.cmd_preview.text()}')

    def updateContainer(self):
        # Destructuring telemetry data
        try:
            TEAM_ID, MISSION_TIME, PACKET_COUNT, PACKET_TYPE, MODE, TP_RELEASED, ALTITUDE, TEMP, VOLTAGE, GPS_TIME, GPS_LATITUDE, GPS_LONGITUDE, GPS_ALTITUDE, GPS_SATS, SOFTWARE_STATE, CMD_ECHO = self.latest_container_telemetry
            self.container_healthy_pkg += 1
            self.ui.c_healthy_pkg_count.setText(
                str(self.container_healthy_pkg))
            with open('Flight_1022_C.csv', 'a') as file:
                file.write(','.join(self.latest_container_telemetry)+'\n')
            with open(f'logs/{self.time_begin}_Flight_1022_C.csv', 'a') as file:
                file.write(','.join(self.latest_container_telemetry)+'\n')

        except Exception:
            self.container_corrupted_pkg += 1
            self.ui.c_corrupted_pkg_count.setText(
                str(self.container_corrupted_pkg))
            logger.warning(
                f'Corrupted packet: {self.latest_container_telemetry}')
            return

        # Update data
        self.c_pkg_data.append(
            self.container_healthy_pkg if settings.PACKET_COUNT_ORIGIN == 'local' else int(PACKET_COUNT))
        self.c_temp_data.append(float(TEMP))
        self.c_altitude_data.append(float(ALTITUDE))
        self.c_gps_altitude_data.append(float(GPS_ALTITUDE))
        self.c_voltage_data.append(float(VOLTAGE))
        self.c_lat_data = GPS_LATITUDE
        self.c_lng_data = GPS_LONGITUDE
        self.ui.c_state.setText(SOFTWARE_STATE)

        # Update state progress bar
        state_progress = 0
        if SOFTWARE_STATE == 'PRELAUNCH':
            state_progress = 1
        elif SOFTWARE_STATE == 'LAUNCH':
            state_progress = 2
        elif SOFTWARE_STATE == 'APOGEE':
            state_progress = 3
        elif SOFTWARE_STATE == 'PARADEPLOY':
            state_progress = 4
        elif SOFTWARE_STATE == 'TPDEPLOY':
            state_progress = 5
        elif SOFTWARE_STATE == 'LAND':
            state_progress = 6
        self.ui.stage_bar.setValue(state_progress)

        # Update chart
        self.c_temp_chart.plot(self.c_pkg_data, self.c_temp_data)
        self.c_altitude_chart .plot(self.c_pkg_data, self.c_altitude_data)
        self.c_gps_altitude_chart .plot(
            self.c_pkg_data, self.c_gps_altitude_data)
        self.c_voltage_chart .plot(self.c_pkg_data, self.c_voltage_data)

        # Update map
        self.ui.lat_value.setText(GPS_LATITUDE)
        self.ui.lng_value.setText(GPS_LONGITUDE)
        self.ui.sats_value.setText(GPS_SATS)
        self.dirloader.appendEarthCoord(Coordinate(
            GPS_LATITUDE, GPS_LONGITUDE, ALTITUDE), color='ff00ff00')
        # Update battery
        bat_percent = self.batteryPercentage(float(VOLTAGE))
        self.ui.container_battery_percent.setText(
            f'{bat_percent.__round__(2)}%')
        self.ui.c_battery_visual.setValue(int(bat_percent))
        # if(bat_percent>70):
        #     self.ui.c_battery_visual.setStyle('background-color: #39d98a')
        # elif(bat_percent>40):
        #     self.ui.c_battery_visual.setStyle('background-color: #ffff00')
        # else:
        #     self.ui.c_battery_visual.setStyle('background-color: #ff0000')

        # self.ui.c_apogee.setText(PRESSURE)

        self.ui.last_cmd_value.setText(CMD_ECHO)

    def updatePayload(self):
        # Destructuring telemetry data
        try:
            TEAM_ID, MISSION_TIME, PACKET_COUNT, PACKET_TYPE, TP_ALTITUDE, TP_TEMP, TP_VOLTAGE, GYRO_R, GYRO_P, GYRO_Y, ACCEL_R, ACCEL_P, ACCEL_Y, MAG_R, MAG_P, MAG_Y, POINTING_ERROR, TP_SOFTWARE_STATE = self.latest_payload_telemetry
            self.payload_healthy_pkg += 1
            self.ui.p_healthy_pkg_count.setText(
                str(self.payload_healthy_pkg))
            with open('Flight_1022_T.csv', 'a') as file:
                file.write(','.join(self.latest_payload_telemetry)+'\n')
            with open(f'logs/{self.time_begin}_Flight_1022_T.csv', 'a') as file:
                file.write(','.join(self.latest_payload_telemetry)+'\n')
        except Exception:
            self.payload_corrupted_pkg += 1
            self.ui.p_corrupted_pkg_count.setText(
                str(self.payload_corrupted_pkg))
            logger.warning(
                f'Corrupted packet: {self.latest_payload_telemetry}')
            return

        # Update data
        self.p_pkg_data.append(
            self.payload_healthy_pkg if settings.PACKET_COUNT_ORIGIN == 'local' else int(PACKET_COUNT))
        self.p_temp_data.append(float(TP_TEMP or -1))
        self.p_altitude_data.append(float(TP_ALTITUDE or -1))
        self.p_gyro_r_data.append(float(GYRO_R))
        self.p_gyro_p_data.append(float(GYRO_P))
        self.p_gyro_y_data.append(float(GYRO_Y))
        self.p_accel_r_data.append(float(ACCEL_R))
        self.p_accel_p_data.append(float(ACCEL_P))
        self.p_accel_y_data.append(float(ACCEL_Y))
        self.p_mag_r_data.append(float(MAG_R))
        self.p_mag_p_data.append(float(MAG_P))
        self.p_mag_y_data.append(float(MAG_Y))
        self.p_ptr_err_data.append(float(POINTING_ERROR))
        self.p_voltage_data.append(float(TP_VOLTAGE))
        self.ui.p_state.setText(TP_SOFTWARE_STATE)

        # Update chart
        self.p_temp_chart.plot(self.p_pkg_data, self.p_temp_data)
        self.p_gyro_chart.plot(
            self.p_pkg_data, (self.p_gyro_r_data, self.p_gyro_p_data, self.p_gyro_y_data))
        self.p_accel_chart.plot(
            self.p_pkg_data, (self.p_accel_r_data, self.p_accel_p_data, self.p_accel_y_data))
        self.p_mag_chart.plot(
            self.p_pkg_data, (self.p_mag_r_data, self.p_mag_p_data, self.p_mag_y_data))
        self.p_ptr_err_chart.plot(self.p_pkg_data, self.p_ptr_err_data)
        self.p_voltage_chart.plot(self.p_pkg_data, self.p_voltage_data)
        self.p_altitude_chart.plot(self.p_pkg_data, self.p_altitude_data)

        # Update battery
        bat_percent = self.batteryPercentage(float(TP_VOLTAGE))
        self.ui.payload_battery_percent.setText(
            f'{bat_percent.__round__(2)}%')
        self.ui.p_battery_visual.setValue(int(bat_percent))

    # def appendData(self, data: list, new_data):
    #     data.append(new_data)
    #     if data.__len__() > 30:
    #         data.pop(0)

    def batteryPercentage(self, voltage: float):
        min_charge = 5.2
        max_charge = 8.3
        percent = ((voltage-min_charge)/(max_charge-min_charge)) * 100
        if percent > 100:
            return 100
        else:
            return percent

    def startSim(self):
        if hasattr(self, 'sim_thread'):
            logger.warning('Sim timer already exist, not starting')
            return
        self.sim_thread = SimThread()
        self.sim_thread.start()

    def stopSim(self):
        if not hasattr(self, 'sim_thread'):
            logger.warn('Sim timer does not exist, not stopping')

    def selectPort(self, port_name: str):
        logger.debug(f'Selecting port name: {port_name}')
        self.current_port = port_name
        if not self.lifecycle_thread.isRunning():
            return
        if hasattr(self, 'telemetry') and self.telemetry is not None:
            self.telemetry.setPort(port_name)
        else:
            self.telemetry = TelemetryHandler(port_name)

    def refreshPort(self):
        logger.debug('Refreshing ports')
        self.ui.port_value.clear()
        self.ui.port_value.addItems(Port.list())

    def selectSimFile(self):
        self.sim_filename, _ = QFileDialog.getOpenFileName(
            filter='CSV Files (*.csv);;All Files (*)', caption='Open simulation file')
        self.ui.sim_file_display.setText(self.sim_filename.split('/')[-1])

    def toggleFullScreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()


class LifecycleThread(QThread):

    # Carriers
    lifecycleRequested = QtCore.Signal(object)

    def __init__(self):
        self._isRunning = True
        # self.setTerminationEnabled(True)
        super(LifecycleThread, self).__init__(None)

    # def __del__(self):
    #     self.wait()

    def run(self):
        logger.info('Lifecycle thread started')
        while True:
            self.lifecycleRequested.emit(None)
            time.sleep(0.001)  # Not to consume too much processing power

    def stop(self):
        logger.info('Lifecycle thread stopping')
        self._isRunning = False
        self.terminate()
        logger.info('Lifecycle thread stopped')


class TelemetryThread(QThread):

    # Carriers
    received = QtCore.Signal(object)
    requestHalt = QtCore.Signal(object)

    def __init__(self):
        self._isRunning = True
        super(TelemetryThread, self).__init__(None)

    # def __del__(self):
    #     self.wait()

    def run(self):
        logger.info('Telemetry thread started')
        while True:
            try:
                incoming_data = window.telemetry.read()
            except DisconnectException:
                self.requestHalt.emit(None)
                return
            self.received.emit(incoming_data)

    def stop(self):
        logger.info('Telemetry thread stopping')
        self._isRunning = False
        self.terminate()
        logger.info('Telemetry thread stopped')


class SimThread(QThread):
    def __init__(self):
        self._isRunning = True
        super(SimThread, self).__init__(None)

    # def __del__(self):
    #     self.wait()

    def run(self):
        logger.info('Sim thread started')
        while True:
            with open(window.sim_filename) as file:
                data = file.readlines()
                for line in data:
                    window.telemetry.sendRawCommand(line)
                    window.ui.telemetry_log.append(f'📨 {line}')
                    time.sleep(1)

    def stop(self):
        logger.info('Sim thread stopping')
        self._isRunning = False
        self.terminate()
        logger.info('Sim thread stopped')


if __name__ == '__main__':
    pg.setConfigOption('foreground', 'w')
    pg.setConfigOption('background', '28293d')
    pg.setConfigOption('antialias', True)
    # pg.setConfigOption('readonly', True)

    app = QtWidgets.QApplication(sys.argv)
    window = App()
    window.showMaximized()
    # window.showFullScreen()
    # app.setQuitOnLastWindowClosed(False)

    # window.updateMap((13.67876, 100.52819))

    try:
        logger.info('Starting window ...')
        sys.exit(app.exec())
    except SystemExit:
        if hasattr(window, 'sim_thread') and window.sim_thread.isRunning():
            window.sim_thread.stop()
        if hasattr(window, 'lifecycle_thread') and window.lifecycle_thread.isRunning():
            window.lifecycle_thread.stop()
        if hasattr(window, 'telemetry_thread') and window.telemetry_thread.isRunning():
            window.telemetry_thread.stop()
        logger.info('Closing window ...')
