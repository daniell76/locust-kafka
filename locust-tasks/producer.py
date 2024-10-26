import logging
import os
import time
from dataclasses import dataclass

from gevent.testing import params
from locust import HttpUser, task, between, events
import random
import string
import subprocess
try:
    from confluent_kafka import Producer, KafkaError, Consumer, KafkaException
except ModuleNotFoundError:
    subprocess.check_call(['pip', 'install', "confluent-kafka"])
    from confluent_kafka import Producer, KafkaError, Consumer, KafkaException


@dataclass
class TestParams:
    def __post_init__(self):
        self.KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "demo-topic")
        self.KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "perf-test")
        self.KAFKA_BYTES_PER_USER = int(os.getenv("KAFKA_BYTES_PER_USER", 104857600))  # default every user generate 100MB data
        self.KAFKA_MSG_SIZE = int(os.getenv("KAFKA_MSG_SIZE", 102400))  # default every message 100KB
        self.KAFKA_MSG_NUM_PER_USER = round(self.KAFKA_BYTES_PER_USER / self.KAFKA_MSG_SIZE)
        if self.KAFKA_MSG_NUM_PER_USER < 1:
            self.KAFKA_MSG_NUM_PER_USER = 1
        self.KAFKA_BYTES_PER_USER = self.KAFKA_MSG_NUM_PER_USER * self.KAFKA_MSG_SIZE
        self.KAFKA_PROD_ACK_ALL = bool(os.getenv("KAFKA_PROD_ACK_ALL", True))  # default ack_all
        self.KAFKA_PROD_RETRIES = int(os.getenv("KAFKA_PROD_RETRIES", -1))  # default not to set
        self.KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
        self.KAFKA_CA_LOCATION = os.getenv("KAFKA_CA_LOCATION", "/test/kafka-auth/ca.crt")
        self.KAFKA_CERT_LOCATION = os.getenv("KAFKA_CERT_LOCATION", "/test/kafka-auth/user.crt")
        self.KAFKA_KEY_LOCATION = os.getenv("KAFKA_KEY_LOCATION", "/test/kafka-auth/user.key")
        self.KAFKA_BATCH_SIZE = int(os.getenv("KAFKA_BATCH_SIZE", -1))
        self.KAFKA_LINGER_MS = int(os.getenv("KAFKA_LINGER_MS", -1))
        self.TEST_BATCH = int(os.getenv("TEST_BATCH", 100))  # number of messages batch to report response time


def generate_random_text(size) -> str:
    characters = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(characters) for i in range(size))


class KafkaProducer(HttpUser):
    wait_time = between(1, 5)
    params = TestParams()
    logger = logging.getLogger(__name__)
    producer = None

    def on_start(self):
        conf_dict = {
            "bootstrap.servers": self.params.KAFKA_BOOTSTRAP_SERVERS,
            "acks": "all" if self.params.KAFKA_PROD_ACK_ALL else "1",
            "enable.ssl.certificate.verification": False
        }
        if self.params.KAFKA_PROD_RETRIES > 0:
            conf_dict["retries"] = self.params.KAFKA_PROD_RETRIES
        if self.params.KAFKA_BATCH_SIZE > 0:
            conf_dict["batch.size"] = self.params.KAFKA_BATCH_SIZE
        if self.params.KAFKA_LINGER_MS > 0:
            conf_dict["linger.ms"] = self.params.KAFKA_LINGER_MS
        if self.params.KAFKA_SECURITY_PROTOCOL != "PLAINTEXT":
            conf_dict["security.protocol"] = self.params.KAFKA_SECURITY_PROTOCOL
            conf_dict["ssl.ca.location"] = self.params.KAFKA_CA_LOCATION
            conf_dict["ssl.certificate.location"] = self.params.KAFKA_CERT_LOCATION
            conf_dict["ssl.key.location"] = self.params.KAFKA_KEY_LOCATION
        self.producer = Producer(conf_dict)  # Create Kafka producer

    @task
    def producer(self):
        message = generate_random_text(self.params.KAFKA_MSG_SIZE)
        total_sent_msg = 0
        while total_sent_msg < self.params.KAFKA_MSG_NUM_PER_USER:
            if total_sent_msg + self.params.TEST_BATCH <= self.params.KAFKA_MSG_NUM_PER_USER:
                n_msg = self.params.TEST_BATCH
            else:
                n_msg = self.params.KAFKA_MSG_NUM_PER_USER - total_sent_msg
            n_successful = 0
            n_failed = 0
            expt = None  # just record the last exception
            start_time = time.time()
            for _ in range(n_msg):
                try:
                    self.producer.produce(self.params.KAFKA_TOPIC, message)
                    self.producer.poll(0)  # Poll for delivery reports
                    n_successful += 1
                except Exception as e:
                    # self.logger.error("Kafka error: %s", e)
                    expt = e
                    n_failed += 1
            response_time = time.time() - start_time
            events.request.fire(
                request_type='kafka', name='produce_message',
                response_length=self.params.KAFKA_MSG_SIZE * n_msg,
                response_time=response_time * 1000, exception=expt)
            total_sent_msg += n_msg
        self.producer.flush()

    def on_stop(self):
        self.producer.flush()

    def graceful_shutdown(self, signum, frame):
        self.on_stop()
        self.environment.runner.quit()