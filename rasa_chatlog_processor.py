import pandas as pd
from datetime import datetime
from utils.helper import *
import datetime
from spelling_correction.heuristic_correction import *
import logging
from underthesea import pos_tag

logging.basicConfig(filename="logging_data/rasa_chatlog_processor_log",
                    format='%(asctime)s %(message)s',
                    filemode='w')
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class RasaChalogProcessor():
    def __init__(self):
        pass

    def get_chatlog_by_month(self, input_month: str, raw_chatlog: str):
        """
        Get chatlog on specific month from raw chatlog from rasa

        :param month: string to indicate month ["01", "02", "03", "04", "05", "06", "07]
        :param raw_chatlog: path to raw chatlog csv file
        """
        logger.info("Get chatlog by month")
        field_name = ['sender_id', 'slots', 'latest_message', 'latest_event_time', 'followup_action', 'paused',
                      'events',
                      'latest_input_channel', 'active_form', 'latest_action_name']
        rasa_conversation = pd.read_csv(raw_chatlog, names=field_name, header=None)
        df_data = {
            "message_id": [],
            "sender_id": [],
            "sender": [],
            "user_message": [],
            "bot_message": [],
            "intent": [],
            "entities": [],
            "created_time": [],
            "attachments": [],

        }
        fmt = "%Y-%m-%d %H:%M:%S"
        for rasa_index, item in rasa_conversation.iterrows():
            if item["events"] is not None and str(item["events"]) != "nan":
                events = literal_eval(item["events"])
            else:
                continue
            sender_id = item["sender_id"]
            # Get user and bot event
            user_bot_events = [x for x in events if x["event"] == "user" or x["event"] == "bot"]
            for event_index, event in enumerate(user_bot_events):
                timestamp = get_timestamp(int(event["timestamp"]), fmt)
                timestamp_month = get_timestamp(int(event["timestamp"]), "%m")
                message_id = ""
                user_intent = ""
                if timestamp_month == input_month:
                    entity_list = ""
                    if "parse_data" in event:
                        if "entities" in event["parse_data"]:
                            entities = event["parse_data"]["entities"]
                            if entities:
                                for item in entities:
                                    if "value" in item:
                                        if item["value"] is not None:
                                            entity_list += item["value"] + ","
                        if "intent" in event["parse_data"]:
                            if "name" in event["parse_data"]["intent"]:
                                user_intent = event['parse_data']['intent']['name']

                    if "message_id" in event:
                        message_id = event["message_id"]

                    message = event["text"]
                    attachments = ""
                    if message is None:
                        message = ""

                    if "scontent" in message:
                        messsage_list = message.split("\n")
                        text_message = ""
                        for item in messsage_list:
                            if "scontent" in item:
                                attachments += item + ", "
                            else:
                                text_message += item + " "
                        message = text_message

                    df_data["entities"].append(entity_list)
                    df_data["sender"].append(event["event"])
                    df_data["intent"].append(user_intent)
                    df_data["message_id"].append(message_id)
                    df_data["sender_id"].append(sender_id)
                    df_data["created_time"].append(timestamp)
                    df_data["attachments"].append(attachments)

                    event_owner = event["event"]
                    if event_owner == "user":
                        df_data["user_message"].append(message)
                        df_data["bot_message"].append("bot")
                    else:
                        df_data["user_message"].append("user")
                        df_data["bot_message"].append(message)

        rasa_chatlog_df = pd.DataFrame.from_dict(df_data)
        output_file_path = "output_data/chatlog_rasa/rasa_chatlog_{month}.csv"
        output_file_path = output_file_path.format(month=input_month)
        rasa_chatlog_df.to_csv(output_file_path, index=False)
        return rasa_chatlog_df

    def split_chatlog_to_conversations(self, rasa_chatlog_df: pd.DataFrame):
        """
       Split chatlog to conversation
       :param fb_conversations:
       :return:
       """
        logger.info("Split chatlog to conversations")
        rasa_chatlog_df.insert(0, 'conversation_id', 0)
        fmt = '%Y-%m-%d %H:%M:%S'
        sender_ids = list(rasa_chatlog_df["sender_id"].dropna())
        sender_ids = sorted(set(sender_ids), key=sender_ids.index)
        conversation_id = 0
        checked_sender_id = []
        for sender_id_index, sender_id in enumerate(sender_ids):
            if sender_id not in checked_sender_id:
                conversation_id += 1
                checked_sender_id.append(sender_id)
            sub_df = rasa_chatlog_df[rasa_chatlog_df["sender_id"] == sender_id].reset_index()
            for index, item in sub_df.iterrows():
                message_index = item["index"]
                rasa_chatlog_df.at[message_index, "conversation_id"] = conversation_id

                if index + 1 < len(sub_df):
                    next_message = sub_df.iloc[index + 1]
                    current_time = item["created_time"][:10] + " " + item["created_time"][11:19]
                    current_time = datetime.datetime.strptime(current_time, fmt)

                    next_time = next_message["created_time"][:10] + " " + next_message["created_time"][11:19]
                    next_time = datetime.datetime.strptime(next_time, fmt)

                    time_diff = (next_time - current_time).total_seconds()
                    if time_diff > 86400:
                        conversation_id += 1
        return rasa_chatlog_df

    def split_chatlog_conversations_to_turns(self, rasa_chatlog_df: pd.DataFrame):
        """
        Split conversations to turns
        :param rasa_chatlog_df:
        :return:
        """
        logger.info("Split conversations to turns")
        rasa_chatlog_df.insert(1, "turn", "")
        conversation_ids = list(rasa_chatlog_df["conversation_id"])
        conversation_ids = list(dict.fromkeys(conversation_ids))
        for conversation_id in conversation_ids:
            sub_df = rasa_chatlog_df[rasa_chatlog_df["conversation_id"] == conversation_id]
            turn = 0
            previous_index = 0
            first_item_in_sub_df = True
            for index, item in sub_df.iterrows():
                if not first_item_in_sub_df:
                    previous_sender_name = sub_df.loc[previous_index]["sender"]
                    current_sender_name = item["sender"]
                    if previous_sender_name == 'bot' and current_sender_name != previous_sender_name:
                        turn += 1
                first_item_in_sub_df = False
                previous_index = index
                rasa_chatlog_df.at[index, "turn"] = turn
        return rasa_chatlog_df

    def set_uc1_and_uc2_for_conversations(self, rasa_chatlog_df: pd.DataFrame):
        # with open("models/ic_for_uc1_2.pkl", "rb") as file:
        #     clf = pickle.load(file)
        conversation_ids = list(rasa_chatlog_df["conversation_id"])
        conversation_ids = list(dict.fromkeys(conversation_ids))
        rasa_chatlog_df.insert(2, "use_case", "")
        for id in conversation_ids:
            chatlog_sub_df = rasa_chatlog_df[rasa_chatlog_df["conversation_id"] == id]
            conversation_attachments = list(chatlog_sub_df['attachments'])
            if any("scontent" in str(x) for x in conversation_attachments):
                chatlog_sub_df_first_turn = chatlog_sub_df[
                    (chatlog_sub_df["turn"] == 0) | (chatlog_sub_df["turn"] == 1)]
                for index, item in chatlog_sub_df_first_turn.iterrows():
                    user_message = item["user_message"]
                    if str(item["entities"]) != "nan":
                        entities_list = item["entities"].split(",")
                        if any("price" in str(x) for x in entities_list):
                            rasa_chatlog_df.at[index, "use_case"] = "uc_2"
                            break
                    if str(user_message) != "nan":
                        user_message_correction = do_correction(user_message)
                        message_pos_tag = pos_tag(user_message_correction)
                        # message_pos_tag = [user_message_correction]

                        ##################################################################
                        words = [x[0] for x in message_pos_tag]
                        pos = [x[1] for x in message_pos_tag]
                        con_x_khong_form = False
                        if "còn" in words and "không" in words:
                            con_index = words.index("còn")
                            khong_index = words.index("không")
                            if con_index < khong_index:
                                in_between_word_pos = pos[con_index:khong_index]
                                """
                                N - Common noun
                                Nc - Noun Classifier
                                Ny - Noun abbreviation
                                Np - Proper noun
                                Nu - Unit noun
                                """
                                if any(x in in_between_word_pos for x in ["N", "Nc", "Ny", "Np", "Nu"]):
                                    con_x_khong_form = True

                        if con_x_khong_form or "còn không" in user_message_correction or (
                                "còn" in user_message_correction and "không" in user_message_correction):
                            rasa_chatlog_df.at[index, "use_case"] = "uc_1"
                            break
                        ##################################################################

                        # input_message = pd.DataFrame([{"feature": user_message_correction}])
                        # predicted = list(clf.predict(input_message["feature"]))
                        # if predicted[0] == "uc_1":
                        #     rasa_chatlog_df.at[index, "use_case"] = "uc_1"
                        # break
        return rasa_chatlog_df

    def specify_conversation_outcome(self, rasa_chatlog_df: pd.DataFrame):
        rasa_chatlog_df.insert(3, "outcome", "")
        uc1_uc2_line = rasa_chatlog_df[
            (rasa_chatlog_df["use_case"] == "uc_1") | (rasa_chatlog_df["use_case"] == "uc_2")]
        conversation_ids = list(uc1_uc2_line["conversation_id"])
        conversation_ids = list(dict.fromkeys(conversation_ids))

        key_words = ["ship", "gửi hàng", "lấy", "địa chỉ", "giao hàng", "đ/c", "thanh toán", "tổng", "stk",
                     "số tài khoản",
                     "gửi về"]
        filter_words = ["địa chỉ shop", "địa chỉ cửa hàng", "lấy rồi", "giao hàng chậm"]

        for id in conversation_ids:
            sub_uc1_uc2_conversation_df = rasa_chatlog_df[rasa_chatlog_df["conversation_id"] == id]
            last_turn = max(list(sub_uc1_uc2_conversation_df["turn"]))
            last_turn_message_df = sub_uc1_uc2_conversation_df[sub_uc1_uc2_conversation_df["turn"] == last_turn]
            last_turn_message_df = last_turn_message_df.dropna(subset=["bot_message"])
            message_counter = 0
            for index, item in last_turn_message_df.iterrows():
                user_message = item["user_message"]
                user_message_correction = False
                if str(user_message) != "nan":
                    user_message_correction = do_correction(user_message)

                bot_message = item["bot_message"]
                user_intent = item["intent"]
                if str(user_intent) != "nan" and user_intent == "thank":
                    rasa_chatlog_df.at[index, "outcome"] = "thank"
                    break
                elif user_message_correction and any(x in user_message_correction for x in key_words) and all(
                        x not in user_message_correction for x in filter_words):
                    rasa_chatlog_df.at[index, "outcome"] = "shipping_order"
                    break
                elif str(user_intent) != "nan" and user_intent == "handover_to_inbox":
                    rasa_chatlog_df.at[index, "outcome"] = "handover_to_inbox"
                    break
                elif str(user_intent) != "nan" and user_intent == "agree":
                    rasa_chatlog_df.at[index, "outcome"] = "agree"
                    break
                elif message_counter == (len(last_turn_message_df) - 1) and item["sender"] == "bot":
                    rasa_chatlog_df.at[index, "outcome"] = "silence"
                    break
                elif message_counter == (len(last_turn_message_df) - 1):
                    rasa_chatlog_df.at[index, "outcome"] = "other"
                    break
                message_counter += 1

        return rasa_chatlog_df

    def process_rasa_chatlog(self, input_month: str, raw_chatlog: str, df: pd.DataFrame):
        """
        Processor
        :param input_month:
        :param raw_chatlog:
        :return:
        """
        logger.info("Start process chatlog")
        rasa_chatlog_by_month_df = df

        # rasa_chatlog_by_month_df = self.get_chatlog_by_month(input_month, raw_chatlog)
        rasa_chatlog_by_month_df = self.split_chatlog_to_conversations(rasa_chatlog_by_month_df)
        rasa_chatlog_by_month_df = self.split_chatlog_conversations_to_turns(rasa_chatlog_by_month_df)
        rasa_chatlog_by_month_df = self.set_uc1_and_uc2_for_conversations(rasa_chatlog_by_month_df)
        rasa_chatlog_by_month_df = self.specify_conversation_outcome(rasa_chatlog_by_month_df)

        output_file_path = "output_data/chatlog_rasa/rasa_chatlog_processed_{month}.csv"
        output_file_path = output_file_path.format(month=input_month)
        # rasa_chatlog_by_month_df.to_csv(output_file_path, index=False)
        return rasa_chatlog_by_month_df
