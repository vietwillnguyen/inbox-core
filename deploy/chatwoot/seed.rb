# Idempotent setup of one client's Chatwoot, run with `rails runner` inside the
# rails container by deploy/chatwoot/stack.sh and deploy/demo/demo.sh.
# Made-up organisation and people only.
# Prints KEY=VALUE lines on stdout, which the scripts write to their gitignored
# .local/tokens.env. Nothing here is a real account.
#
# The organisation's names default to the worked example's. The public demo
# sets them, turns off the test fixtures (a volunteer agent and a second inbox
# for the draft tab's access checks) and widget attachments, and limits the
# pages that may embed the widget.
#
# Telling people, with Chatwoot's own features (docs/chatwoot.md, "Telling a
# person"); each is off unless its variable is set:
#   HANDOFF_ASSIGNEE_EMAIL  an automation rule assigns every hand-off and held
#                           draft nobody has yet to this person, which makes
#                           Chatwoot notify them (in the dashboard, and by email
#                           and push where those are set up).
#   BUSINESS_HOURS          the inbox's working hours, such as
#                           "tue-fri 08:00-18:00, sat 09:00-16:00"; days not
#                           named are closed. With BUSINESS_TIMEZONE (an IANA
#                           name) and OUT_OF_OFFICE_TEXT, Chatwoot sends that
#                           text once a day to a visitor who writes out of hours.
admin_email = ENV.fetch('CHATWOOT_ADMIN_EMAIL')
admin_password = ENV.fetch('CHATWOOT_ADMIN_PASSWORD')
test_fixtures = ENV.fetch('TEST_FIXTURES', 'true') == 'true'
agent_email = ENV.fetch('CHATWOOT_AGENT_EMAIL') if test_fixtures
agent_password = ENV.fetch('CHATWOOT_AGENT_PASSWORD') if test_fixtures
bot_url = ENV.fetch('BOT_OUTGOING_URL')
tab_url = ENV.fetch('DASHBOARD_APP_URL')
widget_origin = ENV.fetch('WIDGET_ORIGIN')
fallback_text = ENV.fetch('FALLBACK_TEXT')
org_name = ENV.fetch('ORG_NAME', 'Brambleford Tool Library')
tagline = ENV.fetch('WIDGET_TAGLINE', 'Ask about opening hours, borrowing and workshops.')
bot_name = ENV.fetch('BOT_NAME', 'Library assistant')
category_labels = ENV.fetch('CATEGORY_LABELS',
                            'faq membership reservation damage_report donation press complaint other').split
attachments = ENV.fetch('WIDGET_ATTACHMENTS', 'true') == 'true'
allowed_domains = ENV.fetch('WIDGET_ALLOWED_DOMAINS', '')
handoff_assignee_email = ENV.fetch('HANDOFF_ASSIGNEE_EMAIL', '')
business_hours = ENV.fetch('BUSINESS_HOURS', '')
business_timezone = ENV.fetch('BUSINESS_TIMEZONE', 'UTC')
out_of_office_text = ENV.fetch('OUT_OF_OFFICE_TEXT', '')

Redis::Alfred.delete(Redis::Alfred::CHATWOOT_INSTALLATION_ONBOARDING)

account = Account.find_or_create_by!(name: org_name)
# No visitor IP addresses on contacts (configs_controller.rb, contact.rb). Off by default; kept off on purpose.
account.disable_features!('ip_lookup')

def person(email, password, name, type = nil)
  user = User.find_by(email: email)
  return user if user

  user = User.new(name: name, email: email, password: password)
  user.type = type if type
  user.skip_confirmation!
  user.save!
  user
end

admin = person(admin_email, admin_password, 'Example Admin', 'SuperAdmin')
AccountUser.find_or_create_by!(account: account, user: admin) { |au| au.role = :administrator }
people = [admin]
if test_fixtures
  agent = person(agent_email, agent_password, 'Example Volunteer')
  AccountUser.find_or_create_by!(account: account, user: agent) { |au| au.role = :agent }
  people << agent
end

# The visitor sees the inbox's name in the widget header, so it is the organisation's.
inbox = account.inboxes.find_by(name: ['Website chat', org_name])
unless inbox
  widget = Channel::WebWidget.create!(account: account, website_url: widget_origin,
                                      welcome_title: org_name, welcome_tagline: tagline)
  inbox = Inbox.create!(account: account, name: org_name, channel: widget)
end
inbox.update!(name: org_name)
# The widget asks for nothing and stores nothing beyond the conversation: no
# transcript emails, no satisfaction survey, and (in the demo) no file uploads.
inbox.channel.update!(welcome_title: org_name, welcome_tagline: tagline, continuity_via_email: false,
                      attachments: attachments, allowed_domains: allowed_domains)
inbox.update!(csat_survey_enabled: false)
people.each { |user| InboxMember.find_or_create_by!(user: user, inbox: inbox) }
# The email-collect prompt posts two template messages with a new conversation,
# and the bot receives those too. When this service is down, each failed
# delivery opens the conversation at the same moment and the fallback rule
# below fires once per opening, so the visitor gets the holding message three
# times. Without the prompt there is one delivery per visitor message.
inbox.update!(enable_email_collect: false)

# A second inbox the volunteer is not a member of, for the draft tab's access checks.
if test_fixtures
  other = account.inboxes.find_by(name: 'Staff only')
  unless other
    channel = Channel::Api.create!(account: account)
    other = Inbox.create!(account: account, name: 'Staff only', channel: channel)
  end
  InboxMember.find_or_create_by!(user: admin, inbox: other)
end

# The visitor sees the bot's name on every answer.
bot = AgentBot.find_by(account: account, name: ['inbox-core', bot_name]) ||
      AgentBot.create!(account: account, name: bot_name)
bot.update!(name: bot_name, outgoing_url: bot_url,
            description: 'inbox-core: guard, triage, handle, deliver, hand off')
abi = AgentBotInbox.find_or_initialize_by(inbox: inbox)
abi.update!(account: account, agent_bot: bot, status: :active)

(%w[inbox-core handoff draft-pending classifier-unavailable inbox-core-unavailable] + category_labels).each do |title|
  account.labels.find_or_create_by!(title: title)
end

app = DashboardApp.find_or_initialize_by(account: account, title: 'inbox-core drafts')
app.user ||= admin
app.content = [{ type: 'frame', url: tab_url }]
app.save!

# When this service is down, Chatwoot opens the conversation itself
# (lib/webhooks/trigger.rb) and tells the visitor nothing. This rule sends the
# visitor a holding message when a conversation is opened with no labels.
# inbox-core labels every conversation it processes ("inbox-core"), and labels
# a hand-off before it opens one, so an agent taking over a conversation the
# bot handled does not trigger it. What is left is a conversation the service
# never saw, opened by Chatwoot's bot-failure path (or by a person from the
# status menu). Conditions on the assignee do not work: inbox auto-assignment
# gives the conversation to an online agent as Chatwoot opens it.
rule = AutomationRule.find_or_initialize_by(account: account, name: 'inbox-core unavailable')
rule.update!(
  description: 'Holding message when the inbox-core service could not be reached',
  event_name: 'conversation_opened',
  active: true,
  conditions: [{ attribute_key: 'labels', filter_operator: 'is_not_present', values: [], query_operator: nil }],
  actions: [
    { action_name: 'send_message', action_params: [fallback_text] },
    { action_name: 'add_label', action_params: ['inbox-core-unavailable'] }
  ]
)

# Hand-off alerts. The bot labels a hand-off ("handoff") or a held draft
# ("draft-pending") and then opens it, and opening it is Chatwoot's
# conversation_opened event. Chatwoot does not notify an assignment made while
# a conversation is still pending (app/listeners/notification_listener.rb), so
# the assignment is made here, once the conversation is open, and only when
# nobody has it: an agent online that inbox auto-assignment already gave it to
# is notified by that assignment instead.
handoff_rule = AutomationRule.find_or_initialize_by(account: account, name: 'inbox-core hand-off')
if handoff_assignee_email.empty?
  handoff_rule.destroy if handoff_rule.persisted?
else
  on_call = User.find_by!(email: handoff_assignee_email)
  InboxMember.find_or_create_by!(user: on_call, inbox: inbox)
  handoff_rule.update!(
    description: 'Assign a hand-off or a held draft nobody has to the person on call, so Chatwoot notifies them',
    event_name: 'conversation_opened',
    active: true,
    conditions: [
      { attribute_key: 'labels', filter_operator: 'equal_to', values: %w[handoff draft-pending], query_operator: 'AND' },
      { attribute_key: 'assignee_id', filter_operator: 'is_not_present', values: [], query_operator: nil }
    ],
    actions: [{ action_name: 'assign_agent', action_params: [on_call.id] }]
  )
  # New account members get these by default (app/models/account_user.rb); set
  # them again so a seed run always leaves the person on call notified.
  setting = NotificationSetting.find_or_create_by!(account: account, user: on_call)
  setting.selected_email_flags = (setting.selected_email_flags | [:email_conversation_assignment])
  setting.selected_push_flags = (setting.selected_push_flags | [:push_conversation_assignment])
  setting.save!
end

# Business hours and the out-of-office reply: Chatwoot's per-inbox working
# hours (app/models/concerns/out_of_offisable.rb). Outside them, a visitor's
# first message of the day gets out_of_office_text as a template message
# (app/services/message_templates/hook_execution_service.rb), which the bot
# ignores; the bot still answers what it can.
if business_hours.empty?
  inbox.update!(working_hours_enabled: false)
else
  days = %w[sun mon tue wed thu fri sat]
  open_days = {}
  business_hours.split(',').map(&:strip).each do |part|
    span, hours = part.split(/\s+/, 2)
    from, to = span.split('-')
    first = days.index(from)
    last = days.index(to || from)
    raise "BUSINESS_HOURS: unknown day in #{part.inspect}" if first.nil? || last.nil?

    match = hours.to_s.match(/\A(\d{2}):(\d{2})-(\d{2}):(\d{2})\z/)
    raise "BUSINESS_HOURS: hours must be HH:MM-HH:MM in #{part.inspect}" unless match

    (first..last).each { |day| open_days[day] = match.captures.map(&:to_i) }
  end
  inbox.update!(working_hours_enabled: true, timezone: business_timezone, out_of_office_message: out_of_office_text)
  (0..6).each do |day|
    hours = inbox.working_hours.find_or_initialize_by(day_of_week: day)
    if open_days[day]
      hours.update!(closed_all_day: false, open_all_day: false, open_hour: open_days[day][0], open_minutes: open_days[day][1],
                    close_hour: open_days[day][2], close_minutes: open_days[day][3])
    else
      hours.update!(closed_all_day: true, open_all_day: false, open_hour: nil, open_minutes: nil,
                    close_hour: nil, close_minutes: nil)
    end
  end
end

puts "CHATWOOT_ACCOUNT_ID=#{account.id}"
puts "CHATWOOT_INBOX_ID=#{inbox.id}"
puts "CHATWOOT_OTHER_INBOX_ID=#{other.id}" if test_fixtures
puts "CHATWOOT_WEBSITE_TOKEN=#{inbox.channel.website_token}"
puts "CHATWOOT_BOT_TOKEN=#{bot.access_token.token}"
puts "CHATWOOT_BOT_SECRET=#{bot.secret}"
puts "CHATWOOT_ADMIN_TOKEN=#{admin.access_token.token}"
puts "CHATWOOT_ADMIN_USER_ID=#{admin.id}"
if test_fixtures
  puts "CHATWOOT_AGENT_TOKEN=#{agent.access_token.token}"
  puts "CHATWOOT_AGENT_USER_ID=#{agent.id}"
end
