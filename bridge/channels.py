from kante.channel import build_channel

from bridge.channel_signals import (
    CallInviteSignal,
    CallParticipantSignal,
    CallSignal,
    StreamSignal,
)

# One group per organization (`stream_group(org)`), on both sides: an agent declaring its
# streams is news for everyone who may watch them.
stream_channel = build_channel(StreamSignal, name="streams")

# Named, so it never receives the stream channel's broadcasts. One group per
# invitee (`call_invite_channel.org_group(org, user.sub)`), on both sides.
call_invite_channel = build_channel(CallInviteSignal, name="call_invites")

# One group per organization (`call_group(org)`), on both sides: a call
# starting, or taking on a new topic, is news for everyone who may join it.
call_channel = build_channel(CallSignal, name="calls")

# One group per call (`participant_group(call)`): who comes and goes is news only for
# whoever watches that one call.
call_participant_channel = build_channel(
    CallParticipantSignal, name="call_participants"
)


def participant_group(call_id: int) -> str:
    """The channel group one call's watchers listen on. One definition, both sides."""
    return f"call_participants.call{call_id}"
