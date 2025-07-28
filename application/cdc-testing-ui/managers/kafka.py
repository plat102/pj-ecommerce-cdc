"""
Kafka Manager for handling CDC event consumption
"""
import json
import time
from datetime import datetime, timedelta
from kafka import KafkaConsumer
from typing import Dict, List
import streamlit as st


class KafkaManager:
    """Handle Kafka operations"""

    def __init__(self, config: Dict):
        self.config = config
        self.consumer = None
        self.producer = None

    def create_consumer(self, topics: List[str], group_id: str = "streamlit-consumer", from_beginning: bool = False):
        """Create Kafka consumer"""
        try:
            if from_beginning:
                group_id = f"{group_id}-recent-{int(time.time())}"
                auto_offset_reset = 'earliest'
            else:
                auto_offset_reset = 'latest'
            
            consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=self.config["bootstrap_servers"],
                group_id=group_id,
                value_deserializer=lambda x: json.loads(x.decode("utf-8")) if x else None,
                key_deserializer=lambda x: x.decode("utf-8") if x else None,
                consumer_timeout_ms=2000,
                auto_offset_reset=auto_offset_reset,
                enable_auto_commit=True,
                auto_commit_interval_ms=1000
            )
            return consumer
        except Exception as e:
            st.error(f"Kafka consumer error: {e}")
            return None

    def consume_messages(self, topics: List[str], max_messages: int = 10, recent_only: bool = False) -> List[Dict]:
        """Consume latest messages from topics"""
        messages = []
        
        if recent_only:
            consumer = self.create_consumer(topics, from_beginning=True)
            target_time = datetime.now() - timedelta(minutes=5)
        else:
            consumer = self.create_consumer(topics, from_beginning=False)
            target_time = None

        if consumer:
            try:
                message_count = 0
                for message in consumer:
                    if message_count >= max_messages:
                        break
                    
                    message_time = datetime.fromtimestamp(message.timestamp / 1000)
                    
                    if recent_only and target_time and message_time < target_time:
                        continue
                    
                    messages.append({
                        "topic": message.topic,
                        "partition": message.partition,
                        "offset": message.offset,
                        "timestamp": message_time,
                        "key": message.key,
                        "value": message.value,
                    })
                    
                    message_count += 1

            except Exception as e:
                st.error(f"Error consuming messages: {e}")
            finally:
                consumer.close()
        
        messages.sort(key=lambda x: x['timestamp'], reverse=True)
        return messages

    def poll_realtime_messages(self, topics: List[str], max_messages: int = 5) -> List[Dict]:
        """Poll for new messages in real-time"""
        messages = []
        consumer = self.create_consumer(topics, from_beginning=False)
        
        if consumer:
            try:
                message_batch = consumer.poll(timeout_ms=100)
                
                for topic_partition, records in message_batch.items():
                    for message in records[-max_messages:]:
                        messages.append({
                            "topic": message.topic,
                            "partition": message.partition,
                            "offset": message.offset,
                            "timestamp": datetime.fromtimestamp(message.timestamp / 1000),
                            "key": message.key,
                            "value": message.value,
                        })
                        
                        if len(messages) >= max_messages:
                            break
                    
                    if len(messages) >= max_messages:
                        break
                        
            except Exception:
                pass
            finally:
                consumer.close()
        
        return sorted(messages, key=lambda x: x['timestamp'], reverse=True)

    def test_connection(self) -> bool:
        """Test Kafka connection"""
        try:
            consumer = self.create_consumer(["__consumer_offsets"])
            if consumer:
                consumer.close()
                return True
            return False
        except Exception:
            return False

    def test_connection(self) -> bool:
        """Test Kafka connection"""
        try:
            consumer = self.create_consumer(["__consumer_offsets"])
            if consumer:
                consumer.close()
                return True
            return False
        except Exception:
            return False

    def get_realtime_consumer(self, topics: List[str]) -> KafkaConsumer:
        """Get or create a persistent consumer for real-time monitoring"""
        try:
            if self.consumer is None or self.consumer.subscription() != set(topics):
                if self.consumer:
                    self.consumer.close()
                
                self.consumer = KafkaConsumer(
                    *topics,
                    bootstrap_servers=self.config["bootstrap_servers"],
                    group_id=f"streamlit-realtime-{int(time.time())}",
                    value_deserializer=lambda x: json.loads(x.decode("utf-8")) if x else None,
                    key_deserializer=lambda x: x.decode("utf-8") if x else None,
                    consumer_timeout_ms=100,
                    auto_offset_reset='latest',
                    enable_auto_commit=False
                )
            
            return self.consumer
        except Exception as e:
            st.error(f"Real-time consumer error: {e}")
            return None

    def poll_realtime_messages(self, topics: List[str], max_messages: int = 5) -> List[Dict]:
        """Poll for new messages in real-time"""
        messages = []
        consumer = self.get_realtime_consumer(topics)
        
        if consumer:
            try:
                message_batch = consumer.poll(timeout_ms=100)
                
                for topic_partition, records in message_batch.items():
                    for message in records[-max_messages:]:
                        messages.append({
                            "topic": message.topic,
                            "partition": message.partition,
                            "offset": message.offset,
                            "timestamp": datetime.fromtimestamp(message.timestamp / 1000),
                            "key": message.key,
                            "value": message.value,
                        })
                        
                        if len(messages) >= max_messages:
                            break
                    
                    if len(messages) >= max_messages:
                        break
                        
            except Exception:
                pass
        
        return sorted(messages, key=lambda x: x['timestamp'], reverse=True)