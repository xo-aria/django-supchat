from django.dispatch import Signal

message_created = Signal()  # args: message, conversation
messages_read = Signal()  # args: conversation, message_ids, reader
conversation_closed = Signal()  # args: conversation, closed_by
conversation_started = Signal()  # args: conversation
conversation_rated = Signal()  # args: conversation, rating
operator_online = Signal()  # args: operator
operator_offline = Signal()  # args: operator
