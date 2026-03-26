"""
<plugin key="DavisApi" name="Davis WeatherLink API v2" author="" version="1.0.0" externallink="https://github.com/jf67-07/domoticz-weatherlink-api">
    <description>
        <h2>Davis Weather Link API v2</h2><br/>
        Connect to Davis weatherlink.com<br />
        <a href="https://weatherlink.github.io/v2-api/">API detail on weatherlink website</a>


    </description>
    <params>
        <param field="Address" label="weatherlink hostnmame" width="450px" required="true" default="api.weatherlink.com" />
        <param field="Mode1" label="API key" width="450px" required="true"/>
        <param field="Mode2" label="API Secret" width="550px" required="true" />
        <param field="Mode4" label="Station ID" width="550px" require="true"/>
        <param field="Mode3" label="Polling intervall (s)" width="200px" default="30" />
        <param field="Mode6" label="Debug" width="150px">
            <options>
                <option label="None" value="0"  default="true" />
                <option label="Python Only" value="2" />
                <option label="Basic Debugging" value="62"/>
                <option label="Basic+Messages" value="126"/>
                <option label="Connections Only" value="16"/>
                <option label="Connections+Python" value="18"/>
                <option label="Connections+Queue" value="144"/>
                <option label="All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import json

class BasePlugin:
    WLConn = None
    Interval = 5*3
    runAgain = Interval
    
    def __init__(self):
        return

    def _openConnection(self):
        if self.WLConn is None:
            self.WLConn = Domoticz.Connection(Name="WLConn", Transport="TCP/IP", Address=Parameters['Address'], Protocol="HTTPS", Port="443")
        self.WLConn.Connect()

    def to_deg(self, value):
        """
            Convert Fahrenheit to Celsius
        """
        return round((value - 32) / 1.8, 1)

    def to_hpa(self, value):
        """
            convert inches of mercury to hPa
        """
        return round(value * 33.8639, 1)


    def wind_deg_to_dir(self, speed, value):
        """
            convert wind diretion in degrees to cardinal point
        """
        if not speed:
            return '0'
        directions = [
            "N", "NNE", "NE", "ENE",
            "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW",
            "W", "WNW", "NW", "NNW" 
        ]
        return directions[int( value / 22.5 + 0.5 ) % 16]


    def miles_per_hour_to_meter_per_sec(self, value):
        return value/2.237

    def get_temp_hum_bar(self, device_id, data):
        if data.get('temp') is not None and data.get('hum') is not None and data.get('bar_sea_level') is not None:
            hum = data['hum']
            bar = self.to_hpa(data['bar_sea_level'])
            temp = self.to_deg(data['temp'])
            if hum < 31:
                humistat = "2"
            elif hum > 69:
                humistat = "3"
            elif hum > 34 and hum < 66 and temp > 21 and temp < 27:
                humistat = "1"
            else:
                humistat = "0"

            UpdateDevice(device_id, 0, str(temp) + ";" + str(data['hum']) + ";" + humistat + ";" + str(bar) + ";0")

    def get_wind(self, device_id, d):
        all_data = ['wind_dir_last', 'wind_speed_last', 'wind_speed_hi_last_10_min', 'temp', 'wind_chill']
        for da in all_data:
            if d.get(da) is None:
                return
        # "<WindDirDegrees>;<WindDirText>;<WindAveMeterPerSecond*10>;<WindGustMeterPerSecond*10>;<Temp_c>;<WindChill_c>"
        UpdateDevice(device_id, 0, 
                                str(d['wind_dir_last']) + ";" 
                                + self.wind_deg_to_dir(d['wind_speed_hi_last_10_min'], d['wind_dir_last']) + ";"
                                + str(self.miles_per_hour_to_meter_per_sec(d['wind_speed_last'])*10) + ";"
                                + str(self.miles_per_hour_to_meter_per_sec(d['wind_speed_hi_last_10_min'])*10) + ";"
                                + str(self.to_deg(d['temp'])) + ";"
                                + str(self.to_deg(d['wind_chill'])))


    def get_radiation(self, device_id, d):
        if d.get('solar_rad') is None:
            return
        UpdateDevice(device_id, 0, d['solar_rad'])

    def get_uv(self, device_id, d):
        for x in ['temp', 'uv_index']:
            if d.get(x) is None:
                return
        UpdateDevice(device_id, 0, str(d['uv_index']) + ';' +  str(self.to_deg(d['temp'])))

    def onStart(self):
        Domoticz.Log("onstart")

        if Parameters["Mode6"] != "0":
            Domoticz.Debugging(int(Parameters["Mode6"]))
            DumpConfigToLog()
        Domoticz.Log("mode 6:" + Parameters["Mode6"])
        self.Interval = int(Parameters["Mode3"])/10
        self.runAgain = self.Interval
        self._openConnection()
        Domoticz.Log("Sended connect")

        self.devices = [
                {'Name': 'Temperature', 'TypeName': 'Temp+Hum+Baro', 'data': 'get_temp_hum_bar'},  
                {'Name': 'Vent', 'TypeName': 'Wind', 'SubTypeName': 'Wind+Temp+Chill ', 'data': 'get_wind'},  
                {'Name': 'Radiations Solaire', 'TypeName': 'Solar Radiation', 'SubTypeName': 'Solar Radiation', 'data': 'get_radiation'},
                {'Name': 'UV', 'TypeName': 'UV', 'data': 'get_uv'},

        ]
        Domoticz.Log(Devices)

        idx = 1
        for x in self.devices:
            if idx not in Devices:
                Domoticz.Device(Name=x['Name'], Unit=idx, TypeName=x['TypeName']).Create()

            idx += 1
        Domoticz.Heartbeat(10)

    def onStop(self):
        Domoticz.Log("onStop - Plugin is stopping.")

    def onConnect(self, Connection, Status, Description):
        if (Status == 0):
            Domoticz.Debug("Connected successfully. Getting")
            sendData = { 
                'Verb' : 'GET',
                'URL'  :  f"/v2/current/{Parameters['Mode4']}?api-key={Parameters['Mode1']}", 
                'Headers' : { 
                    'User-Agent':'Domoticz/1.0',
                    'x-api-secret': Parameters['Mode2'],
                    'Host' : Parameters['Address'],
                },
            }
            Connection.Send(sendData)
        else:
            Domoticz.Log("Failed to connect ("+str(Status)+") to: "+Parameters["Address"]+":"+Parameters["Mode1"]+" with error: "+Description) 
    

    def onMessage(self, Connection, Data):
        Domoticz.Debug('%s %s'% (Data, Data.get('Status')))
        strData = Data['Data'].decode("utf-8", "ignore")
        Response = json.loads(strData)

        self.WLConn.Disconnect()

        Status = Data.get('Status')
        if Status == '200':
            Domoticz.Log("Good Response received from Davis, Disconnecting.")
            all_data = {}
            for sensor in Response.get('sensors', []):
                if sensor.get('data'):
                    all_data.update(sensor['data'][0])

            idx = 1
            for x in self.devices:
                if x.get('data'):
                    getattr(self, x['data'])(idx, all_data)
                idx += 1
        elif Status == '400':
            Domoticz.Error("WL returned a Bad Request Error.")
        elif Status == '500':
            Domoticz.Error("WL returned a Server Error.")
        else:
            Domoticz.Error("WL returned a status: "+str(Status))

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onDisconnect(self, Connection):
        Domoticz.Log("onDisconnect called for connection to: "+Connection.Address+":"+Connection.Port)

    def onHeartbeat(self):
        Domoticz.Log("HeatBeat")
        if (self.WLConn != None and (self.WLConn.Connecting() or self.WLConn.Connected())):
            Domoticz.Debug("onHeartbeat called, Connection is alive.")
        else:
            self.runAgain = self.runAgain - 1
            if self.runAgain <= 0:
                self._openConnection()
                self.runAgain = self.Interval
            else:
                Domoticz.Debug("onHeartbeat called, run again in "+str(self.runAgain)+" heartbeats.")

global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def UpdateDevice(Unit, nValue, sValue):
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue):
            Devices[Unit].Update(nValue=nValue, sValue=str(sValue))
    return

# Generic helper functions
def LogMessage(Message):
    if Parameters["Mode6"] == "File":
        f = open(Parameters["HomeFolder"]+"HTTPS.html","w")
        f.write(Message)
        f.close()
        Domoticz.Log("File written")

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

def DumpHTTPSResponseToLog(HTTPSResp, level=0):
    if (level==0): Domoticz.Debug("HTTPS Details ("+str(len(HTTPSResp))+"):")
    indentStr = ""
    for x in range(level):
        indentStr += "----"
    if isinstance(HTTPSResp, dict):
        for x in HTTPSResp:
            if not isinstance(HTTPSResp[x], dict) and not isinstance(HTTPSResp[x], list):
                Domoticz.Debug(indentStr + ">'" + x + "':'" + str(HTTPSResp[x]) + "'")
            else:
                Domoticz.Debug(indentStr + ">'" + x + "':")
                DumpHTTPSResponseToLog(HTTPSResp[x], level+1)
    elif isinstance(HTTPSResp, list):
        for x in HTTPSResp:
            Domoticz.Debug(indentStr + "['" + x + "']")
    else:
        Domoticz.Debug(indentStr + ">'" + x + "':'" + str(HTTPSResp[x]) + "'")
