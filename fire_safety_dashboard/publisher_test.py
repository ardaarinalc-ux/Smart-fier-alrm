import time
import json
import random
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883

def publish_loop():
    client = mqtt.Client()
    try:
        client.connect(BROKER, PORT, 60)
        print("Connected to broker")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    # Periodically publish
    try:
        while True:
            # Random gas value between 200 and 3000
            gas_val = random.randint(200, 3000)
            client.publish("sensor/gas", json.dumps({"nilai": gas_val}))
            print(f"Published gas: {gas_val}")

            # Random temperature and humidity
            temp_val = round(random.uniform(20.0, 45.0), 1)
            hum_val = round(random.uniform(30.0, 90.0), 1)
            client.publish("sensor/suhu", json.dumps({"suhu": temp_val, "humidity": hum_val}))
            print(f"Published temp/hum: {temp_val} C, {hum_val}%")

            # Occasionally send RFID
            if random.random() < 0.2:
                rfid = random.choice(["3A:5F:9C:21", "E2:80:68:1A", "UNKNOWN_CARD"])
                client.publish("sistem/rfid", json.dumps({"rfid": rfid}))
                print(f"Published RFID: {rfid}")

            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping publisher...")
    finally:
        client.disconnect()

if __name__ == "__main__":
    publish_loop()