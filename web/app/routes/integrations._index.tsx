import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertTitle,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Code as CodeChip,
  CopyableCode,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Flex,
  Grid,
  Heading,
  IconTile,
  Input,
  Label,
  ListRow,
  ListRowGroup,
  ListRowItem,
  PageSection,
  PageToolbar,
  PluginCard,
  PluginCategoryBadge,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Stack,
  StatusDot,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { EmptyState } from "@fiestaboard/ui/components/feedback/empty-state";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlarmClock,
  AlertCircle,
  Ambulance,
  Anchor,
  Apple,
  ArrowDown,
  ArrowDownToLine,
  ArrowUp,
  Award,
  BarChart,
  Battery,
  BatteryCharging,
  Beer,
  Bell,
  Bike,
  Bird,
  Bitcoin,
  Bluetooth,
  Bookmark,
  BookOpen,
  Bot,
  Box as BoxIcon,
  Bug,
  Building,
  Building2,
  Cake,
  Calendar,
  CalendarClock,
  CalendarDays,
  Camera,
  Car,
  Cat,
  Check,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  ChevronsUp,
  ChevronUp,
  Church,
  Clock,
  Cloud,
  CloudRain,
  CloudSnow,
  CloudSun,
  Code,
  Coffee,
  Cog,
  Compass,
  Cookie,
  CopyPlus,
  Cpu,
  Crown,
  CupSoda,
  Database,
  Dog,
  DollarSign,
  Download,
  Droplets,
  Dumbbell,
  ExternalLink,
  Eye,
  EyeOff,
  Factory,
  Fan,
  Film,
  Filter,
  Fish,
  Flag,
  Flame,
  Flower,
  Flower2,
  Gamepad2,
  Gem,
  Ghost,
  Gift,
  GitBranch,
  GlassWater,
  Globe,
  GraduationCap,
  Hammer,
  HardDrive,
  Headphones,
  Heart,
  History,
  Home,
  Hourglass,
  IceCream,
  Image,
  Key,
  Landmark,
  Laptop,
  LayoutGrid,
  LayoutList,
  Leaf,
  Library,
  Lightbulb,
  LineChart,
  Link as LinkIcon,
  Lock,
  Mail,
  Map,
  MapPin,
  Megaphone,
  MessageCircle,
  MessageSquare,
  Mic,
  Monitor,
  Moon,
  MoreHorizontal,
  Mountain,
  Music,
  Navigation,
  Newspaper,
  Package,
  PartyPopper,
  Pause,
  Phone,
  PieChart,
  Pill,
  Pin,
  Pizza,
  Plane,
  Play,
  Plus,
  Power,
  Puzzle,
  QrCode,
  Radio,
  RefreshCw,
  Rocket,
  Route,
  Rss,
  Satellite,
  School,
  Search,
  Send,
  Server,
  Settings,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Ship,
  ShoppingCart,
  Signpost,
  Skull,
  Smartphone,
  Smile,
  Snowflake,
  Sparkles,
  Speaker,
  Sprout,
  Star,
  Stethoscope,
  Store,
  Sun,
  Sunrise,
  Sunset,
  Tag,
  Tags,
  Target,
  Tent,
  Terminal,
  Thermometer,
  Timer,
  TrainFront,
  Trash2,
  TreePine,
  Trees,
  TrendingUp,
  Trophy,
  Tv,
  Umbrella,
  Unlock,
  Upload,
  UserCircle,
  Users,
  Video,
  Volume2,
  Wand,
  Wand2,
  Warehouse,
  Watch,
  Waves,
  Wifi,
  WifiOff,
  Wind,
  Wine,
  Wrench,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import type { ReactNode, RefObject } from "react";
import { Fragment, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { UNSAFE_DataRouterContext, useBeforeUnload, useBlocker } from "react-router";
import { toast } from "sonner";

import { IntegrationBoardPreview } from "@/components/integrations/integration-board-preview";
import { IntegrationReadme } from "@/components/integrations/integration-readme";
import { GitInstallFields, useGitPluginInstall } from "@/components/plugin-git-install";
import { PluginProvenance } from "@/components/plugin-provenance";
import {
  asJSONSchema,
  findOAuthConnection,
  mapConfigErrors,
  OAUTH_CONNECTIONS_QUERY_KEY,
  oauthAppFieldKeys,
  OAuthConnectionSection,
  oauthReturnErrorKey,
  pluginConfigErrors,
  readOAuthReturn,
  SchemaForm,
} from "@/components/plugin-settings";
import { PluginAutoUpdateSwitch, PluginUpdateCheckButton } from "@/components/plugin-updates-control";
import Link from "@/components/smart-link";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useEffectiveBoardColor } from "@/hooks/use-effective-board-color";
import { useEffectiveCode62Glyph } from "@/hooks/use-effective-code62-glyph";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { OAuthConnection, PluginInfo, RegistryEntry } from "@/lib/api";
import { api } from "@/lib/api";
import type { FiestaboardColorName } from "@/lib/board-colors";
import { ALL_COLOR_CODES, AVAILABLE_COLORS, FIESTABOARD_COLORS } from "@/lib/board-colors";
import {
  buildVariablesList,
  getVariableGroups,
  groupVariableRows,
  type PluginVariableRow,
  type VariablesBlock,
} from "@/lib/plugin-variables";
import { cn } from "@/lib/utils";

/**
 * Comprehensive icon mapping from Lucide icon names to components.
 * Plugins can specify any of these icons in their manifest.json.
 */
const ICON_MAP: Record<string, LucideIcon> = {
  // Weather & Environment
  cloud: Cloud,
  sun: Sun,
  moon: Moon,
  thermometer: Thermometer,
  droplets: Droplets,
  wind: Wind,
  umbrella: Umbrella,
  cloud_rain: CloudRain,
  cloudrain: CloudRain,
  cloud_snow: CloudSnow,
  cloudsnow: CloudSnow,
  cloud_sun: CloudSun,
  cloudsun: CloudSun,
  sunrise: Sunrise,
  sunset: Sunset,
  snowflake: Snowflake,
  flame: Flame,
  waves: Waves,

  // Transportation
  car: Car,
  bike: Bike,
  train: TrainFront,
  train_front: TrainFront,
  trainfront: TrainFront,
  plane: Plane,
  ship: Ship,
  rocket: Rocket,
  anchor: Anchor,
  navigation: Navigation,
  map_pin: MapPin,
  mappin: MapPin,
  compass: Compass,
  map: Map,
  route: Route,
  signpost: Signpost,

  // Home & Smart Home
  home: Home,
  lightbulb: Lightbulb,
  fan: Fan,
  power: Power,
  battery: Battery,
  battery_charging: BatteryCharging,
  batterycharging: BatteryCharging,
  wifi: Wifi,
  wifi_off: WifiOff,
  wifioff: WifiOff,
  bluetooth: Bluetooth,
  lock: Lock,
  unlock: Unlock,
  key: Key,
  shield: Shield,
  shield_check: ShieldCheck,
  shieldcheck: ShieldCheck,

  // Time & Calendar
  calendar: Calendar,
  calendar_days: CalendarDays,
  calendardays: CalendarDays,
  calendar_clock: CalendarClock,
  calendarclock: CalendarClock,
  clock: Clock,
  alarm_clock: AlarmClock,
  alarmclock: AlarmClock,
  timer: Timer,
  hourglass: Hourglass,
  watch: Watch,
  history: History,

  // Finance
  trending_up: TrendingUp,
  trendingup: TrendingUp,
  dollar_sign: DollarSign,
  dollarsign: DollarSign,
  bitcoin: Bitcoin,
  bar_chart: BarChart,
  barchart: BarChart,
  pie_chart: PieChart,
  piechart: PieChart,
  line_chart: LineChart,
  linechart: LineChart,
  activity: Activity,

  // Entertainment
  sparkles: Sparkles,
  music: Music,
  film: Film,
  gamepad2: Gamepad2,
  tv: Tv,
  radio: Radio,
  headphones: Headphones,
  speaker: Speaker,
  volume2: Volume2,
  play: Play,
  pause: Pause,
  party_popper: PartyPopper,
  partypopper: PartyPopper,

  // Communication
  message_square: MessageSquare,
  messagesquare: MessageSquare,
  message_circle: MessageCircle,
  messagecircle: MessageCircle,
  mail: Mail,
  phone: Phone,
  bell: Bell,
  megaphone: Megaphone,
  send: Send,
  rss: Rss,

  // Technology
  smartphone: Smartphone,
  laptop: Laptop,
  monitor: Monitor,
  cpu: Cpu,
  hard_drive: HardDrive,
  harddrive: HardDrive,
  server: Server,
  database: Database,
  globe: Globe,
  code: Code,
  terminal: Terminal,
  bot: Bot,
  satellite: Satellite,
  qr_code: QrCode,
  qrcode: QrCode,

  // Health & Fitness
  heart: Heart,
  activity2: Activity,
  dumbbell: Dumbbell,
  pill: Pill,
  stethoscope: Stethoscope,
  ambulance: Ambulance,
  apple: Apple,

  // Nature
  leaf: Leaf,
  tree_pine: TreePine,
  treepine: TreePine,
  flower2: Flower2,
  flower: Flower,
  sprout: Sprout,
  mountain: Mountain,
  trees: Trees,
  bug: Bug,
  fish: Fish,
  bird: Bird,
  dog: Dog,
  cat: Cat,

  // Food & Drink
  coffee: Coffee,
  pizza: Pizza,
  cake: Cake,
  cookie: Cookie,
  ice_cream: IceCream,
  icecream: IceCream,
  beer: Beer,
  wine: Wine,
  glass_water: GlassWater,
  glasswater: GlassWater,
  cup_soda: CupSoda,
  cupsoda: CupSoda,

  // Places
  building: Building,
  building2: Building2,
  factory: Factory,
  store: Store,
  warehouse: Warehouse,
  school: School,
  library: Library,
  landmark: Landmark,
  church: Church,
  tent: Tent,

  // Shopping
  shopping_cart: ShoppingCart,
  shoppingcart: ShoppingCart,
  package: Package,
  gift: Gift,
  tag: Tag,
  tags: Tags,

  // Actions & UI
  settings: Settings,
  cog: Cog,
  wrench: Wrench,
  hammer: Hammer,
  search: Search,
  filter: Filter,
  refresh_cw: RefreshCw,
  refreshcw: RefreshCw,
  download: Download,
  upload: Upload,
  eye: Eye,
  eye_off: EyeOff,
  eyeoff: EyeOff,

  // Status
  check_circle: CheckCircle,
  checkcircle: CheckCircle,
  alert_circle: AlertCircle,
  alertcircle: AlertCircle,
  x_circle: XCircle,
  xcircle: XCircle,
  check: Check,
  x: X,

  // Miscellaneous
  star: Star,
  award: Award,
  trophy: Trophy,
  target: Target,
  flag: Flag,
  bookmark: Bookmark,
  pin: Pin,
  link: LinkIcon,
  external_link: ExternalLink,
  externallink: ExternalLink,
  user_circle: UserCircle,
  usercircle: UserCircle,
  users: Users,
  zap: Zap,
  gem: Gem,
  crown: Crown,
  wand: Wand,
  wand2: Wand2,
  ghost: Ghost,
  skull: Skull,
  smile: Smile,
  book_open: BookOpen,
  bookopen: BookOpen,
  newspaper: Newspaper,
  graduation_cap: GraduationCap,
  graduationcap: GraduationCap,
  camera: Camera,
  image: Image,
  video: Video,
  mic: Mic,

  // Default fallback
  puzzle: Puzzle,
};

/**
 * Normalize a plugin manifest icon field into an `ICON_MAP` key
 * (lowercase, snake_case). Used to look up the Lucide icon component
 * for a plugin, falling back to Puzzle if not found.
 *
 * This resolves the map *key* rather than the component itself so
 * callers can do a plain `ICON_MAP[key] ?? Puzzle` lookup inline —
 * assigning a function's return value directly to a capitalized
 * variable used as a JSX tag defines a new component reference during
 * render (see React Compiler's "Cannot create components during
 * render" rule).
 */
function normalizePluginIconKey(iconName?: string): string {
  if (!iconName) return "";

  // Normalize: lowercase and handle both snake_case and lowercase
  return iconName.toLowerCase().replace(/-/g, "_");
}

// Color display helpers - using board's official colors
const COLOR_DISPLAY: Record<FiestaboardColorName, { bg: string; text: string; hex: string }> = {
  red: { bg: "bg-board-red", text: "text-board-white", hex: FIESTABOARD_COLORS.red },
  orange: { bg: "bg-board-orange", text: "text-board-black", hex: FIESTABOARD_COLORS.orange },
  yellow: { bg: "bg-board-yellow", text: "text-board-black", hex: FIESTABOARD_COLORS.yellow },
  green: { bg: "bg-board-green", text: "text-board-black", hex: FIESTABOARD_COLORS.green },
  blue: { bg: "bg-board-blue", text: "text-board-white", hex: FIESTABOARD_COLORS.blue },
  violet: { bg: "bg-board-violet", text: "text-board-white", hex: FIESTABOARD_COLORS.violet },
  white: { bg: "bg-board-white border", text: "text-board-black", hex: FIESTABOARD_COLORS.white },
  black: { bg: "bg-board-black", text: "text-board-white", hex: FIESTABOARD_COLORS.black },
};

// Available conditions for color rules
const AVAILABLE_CONDITIONS = [
  { value: ">=", label: ">= (greater or equal)" },
  { value: "<=", label: "<= (less or equal)" },
  { value: ">", label: "> (greater than)" },
  { value: "<", label: "< (less than)" },
  { value: "==", label: "== (equals)" },
  { value: "!=", label: "!= (not equals)" },
];

// Color rule types
interface ColorRule {
  condition: string;
  value: string | number;
  color: string;
}

interface ColorRulesConfig {
  [fieldName: string]: ColorRule[];
}

// Color Rules Editor Component
function ColorRulesEditor({
  pluginId,
  colorRules,
  onChange,
  onVarCopied,
}: {
  pluginId: string;
  colorRules: ColorRulesConfig;
  onChange: (rules: ColorRulesConfig) => void;
  onVarCopied: (templateVar: string) => void;
}) {
  const t = useTranslations("integrations");
  const tCommon = useTranslations("common");
  const [newFieldName, setNewFieldName] = useState("");
  const [showAddField, setShowAddField] = useState(false);

  const handleUpdateRule = (fieldName: string, ruleIndex: number, updates: Partial<ColorRule>) => {
    const newRules = { ...colorRules };
    newRules[fieldName] = [...newRules[fieldName]];
    newRules[fieldName][ruleIndex] = { ...newRules[fieldName][ruleIndex], ...updates };
    onChange(newRules);
  };

  const handleDeleteRule = (fieldName: string, ruleIndex: number) => {
    const newRules = { ...colorRules };
    newRules[fieldName] = newRules[fieldName].filter((_, i) => i !== ruleIndex);
    if (newRules[fieldName].length === 0) {
      delete newRules[fieldName];
    }
    onChange(newRules);
  };

  const handleAddRule = (fieldName: string) => {
    const newRules = { ...colorRules };
    if (!newRules[fieldName]) {
      newRules[fieldName] = [];
    }
    newRules[fieldName] = [...newRules[fieldName], { condition: ">=", value: 0, color: "green" }];
    onChange(newRules);
  };

  const handleMoveRule = (fieldName: string, ruleIndex: number, direction: "up" | "down") => {
    const newRules = { ...colorRules };
    const rules = [...newRules[fieldName]];
    const newIndex = direction === "up" ? ruleIndex - 1 : ruleIndex + 1;
    if (newIndex < 0 || newIndex >= rules.length) return;
    [rules[ruleIndex], rules[newIndex]] = [rules[newIndex], rules[ruleIndex]];
    newRules[fieldName] = rules;
    onChange(newRules);
  };

  const handleAddField = () => {
    if (!newFieldName.trim()) return;
    const newRules = { ...colorRules };
    newRules[newFieldName.trim()] = [{ condition: ">=", value: 0, color: "green" }];
    onChange(newRules);
    setNewFieldName("");
    setShowAddField(false);
  };

  const handleDeleteField = (fieldName: string) => {
    const newRules = { ...colorRules };
    delete newRules[fieldName];
    onChange(newRules);
  };

  const fieldNames = Object.keys(colorRules);

  return (
    <TooltipProvider>
      <Stack gap="3">
        <Flex align="center" justify="between">
          <Heading level={4} size="sm" className="font-medium text-muted-foreground">
            {t("colorRules.title")}
            <Text as="span" size="xs" tone="muted" className="ml-2">
              ({t("colorRules.firstMatchWins")})
            </Text>
          </Heading>
          <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setShowAddField(!showAddField)}>
            <Plus className="h-3 w-3 mr-1" />
            {t("colorRules.addField")}
          </Button>
        </Flex>

        {/* Add new field input */}
        {showAddField && (
          <Flex gap="2" className="p-2 rounded-md border bg-muted/30">
            <Input
              type="text"
              value={newFieldName}
              onChange={(e) => setNewFieldName(e.target.value)}
              placeholder={t("colorRules.fieldPlaceholder")}
              className="flex-1 h-8 px-2 text-xs rounded bg-background shadow-none"
            />
            <Button size="sm" className="h-8 text-xs" onClick={handleAddField}>
              {tCommon("add")}
            </Button>
            <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setShowAddField(false)}>
              {tCommon("cancel")}
            </Button>
          </Flex>
        )}

        {fieldNames.length === 0 ? (
          <Text size="xs" tone="muted" className="py-2">
            {t("colorRules.noRulesConfigured")}
          </Text>
        ) : (
          <Stack gap="3">
            {fieldNames.map((fieldName) => {
              const rules = colorRules[fieldName];
              return (
                <Box key={fieldName} className="rounded-md border overflow-hidden">
                  {/* Field header */}
                  <Flex align="center" justify="between" className="bg-muted/50 px-3 py-2">
                    <Flex align="center" gap="2">
                      <CodeChip className="text-primary bg-primary/10">
                        {pluginId}.{fieldName}
                      </CodeChip>
                      <Text as="span" size="xs" tone="muted">
                        {t("colorRules.colorBasedOnValue")}
                      </Text>
                    </Flex>
                    <Flex align="center" gap="1">
                      <CopyableCode
                        value={`{{${pluginId}.${fieldName}_color}}`}
                        onCopied={onVarCopied}
                        className="bg-transparent text-muted-foreground hover:text-foreground hover:bg-muted"
                      >
                        {`${fieldName}_color`}
                      </CopyableCode>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            onClick={() => handleDeleteField(fieldName)}
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <Text>{t("colorRules.deleteFieldTooltip")}</Text>
                        </TooltipContent>
                      </Tooltip>
                    </Flex>
                  </Flex>

                  {/* Rules */}
                  <Box className="divide-y">
                    {rules.map((rule, idx) => {
                      const colorStyle = COLOR_DISPLAY[rule.color as FiestaboardColorName] || {
                        bg: "bg-muted",
                        text: "text-muted-foreground",
                        hex: "#6b7280",
                      };
                      return (
                        <Flex key={idx} align="center" gap="2" className="px-3 py-2 text-xs">
                          {/* Reorder buttons */}
                          <Flex direction="col" gap="0.5">
                            <button
                              onClick={() => handleMoveRule(fieldName, idx, "up")}
                              disabled={idx === 0}
                              className="p-0.5 hover:bg-muted rounded disabled:opacity-50"
                            >
                              <ArrowUp className="h-3 w-3" />
                            </button>
                            <button
                              onClick={() => handleMoveRule(fieldName, idx, "down")}
                              disabled={idx === rules.length - 1}
                              className="p-0.5 hover:bg-muted rounded disabled:opacity-50"
                            >
                              <ArrowDown className="h-3 w-3" />
                            </button>
                          </Flex>

                          {/* Color picker */}
                          <Select
                            value={rule.color}
                            onValueChange={(color) => handleUpdateRule(fieldName, idx, { color })}
                          >
                            <SelectTrigger
                              className="h-7 w-auto px-2 text-xs font-medium [&_svg]:text-current"
                              style={{
                                backgroundColor: colorStyle.hex,
                                color: colorStyle.text === "text-board-black" ? "#000" : "#fff",
                              }}
                            >
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {AVAILABLE_COLORS.map((color) => (
                                <SelectItem key={color} value={color}>
                                  {color}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>

                          <Text as="span" size="xs" tone="muted" className="shrink-0">
                            {t("colorRules.when")}
                          </Text>

                          {/* Condition picker */}
                          <Select
                            value={rule.condition}
                            onValueChange={(condition) => handleUpdateRule(fieldName, idx, { condition })}
                          >
                            <SelectTrigger className="h-7 w-auto px-2 text-xs font-mono">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              {AVAILABLE_CONDITIONS.map((cond) => (
                                <SelectItem key={cond.value} value={cond.value} className="font-mono">
                                  {cond.value}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>

                          {/* Value input */}
                          <Input
                            type="text"
                            value={rule.value}
                            onChange={(e) => {
                              const val = e.target.value;
                              // Try to parse as number, otherwise keep as string
                              const numVal = parseFloat(val);
                              handleUpdateRule(fieldName, idx, {
                                value: isNaN(numVal) ? val : numVal,
                              });
                            }}
                            className="w-20 h-7 px-2 rounded bg-background text-xs font-mono shadow-none"
                            placeholder={t("colorRules.valuePlaceholder")}
                          />

                          {/* Delete button */}
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            onClick={() => handleDeleteRule(fieldName, idx)}
                            className="ml-auto text-destructive hover:bg-destructive/10 hover:text-destructive"
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </Flex>
                      );
                    })}
                  </Box>

                  {/* Add rule button */}
                  <Box className="px-3 py-2 border-t bg-muted/20">
                    <button
                      onClick={() => handleAddRule(fieldName)}
                      className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                    >
                      <Plus className="h-3 w-3" />
                      {t("colorRules.addRule")}
                    </button>
                  </Box>
                </Box>
              );
            })}
          </Stack>
        )}

        <Text size="xs" tone="muted">
          {t("colorRules.ruleDescription", { example: `{{${pluginId}.field_color}}` })}
        </Text>
      </Stack>
    </TooltipProvider>
  );
}

// Category ids that have a translated label. Anything else falls back to the
// raw manifest category string at the call site.
const CATEGORY_KEYS = [
  "art",
  "data",
  "entertainment",
  "finance",
  "home",
  "output",
  "transit",
  "transition",
  "utility",
  "weather",
] as const;

/**
 * Category id → display label, sourced from `integrations.categories` so the
 * chips, the sort keys and the marketplace section headings all read the same
 * translated string.
 */
function useCategoryLabels(): Record<string, string> {
  const t = useTranslations("integrations");
  return Object.fromEntries(CATEGORY_KEYS.map((key) => [key, t(`categories.${key}`)]));
}

// Resolve the live value of a template variable from a plugin's raw display data.
// Variable names come in two shapes:
//   - simple:  "temperature"             → data.temperature
//   - array:   "forecast.{index}.day"    → data.forecast[i].day for each i
// Returns null when the variable can't be resolved (missing key, plugin disabled).
// `short` is what we render in the cell; `full` is what the hover tooltip shows.
function formatCurrentValue(
  variable: string,
  data: Record<string, unknown> | undefined,
): { short: string; full: string } | null {
  if (!data) return null;

  const stringify = (v: unknown): string => {
    if (v == null) return "";
    if (typeof v === "string") return v;
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  };

  // Array variable: "<arrayName>.{index}.<field>"
  const arrayMatch = variable.match(/^([^.]+)\.\{index\}\.(.+)$/);
  if (arrayMatch) {
    const [, arrayName, field] = arrayMatch;
    const arr = data[arrayName];
    if (!Array.isArray(arr) || arr.length === 0) return null;

    const entries = arr.map((item, i) => {
      const value = item && typeof item === "object" ? (item as Record<string, unknown>)[field] : undefined;
      return { i, value: stringify(value) };
    });

    const fullLines = entries.map(({ i, value }) => `[${i}] ${value || "—"}`);
    const previewCount = 3;
    const previewParts = entries.slice(0, previewCount).map(({ i, value }) => `[${i}] ${value || "—"}`);
    const more = entries.length > previewCount ? `  +${entries.length - previewCount} more` : "";

    return { short: previewParts.join("  ") + more, full: fullLines.join("\n") };
  }

  // Simple variable: direct key lookup.
  if (!(variable in data)) return null;
  const value = stringify(data[variable]);
  return { short: value, full: value };
}

// Render a value string with inline color swatches in place of `{63}` / `{red}`
// tokens, mirroring how the board preview parses lines. End tags `{/...}` are
// dropped. Non-color text passes through unchanged so mixed strings like
// "Sunny {66}*{/}" render as text + a green tile.
function renderValueWithColors(value: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let i = 0;
  let key = 0;
  let textBuf = "";
  const flushText = () => {
    if (textBuf) {
      // Rendered inline into caller-supplied text contexts with varying ambient
      // size/color (font-mono chips, tooltip content, table cells) — Text's fixed
      // defaults would override whichever context this lands in, so this stays raw.
      // eslint-disable-next-line react/forbid-elements -- inherit-only span rendered into varied ambient text contexts; Text's fixed size/tone defaults would override the caller's context
      nodes.push(<span key={`t${key++}`}>{textBuf}</span>);
      textBuf = "";
    }
  };
  while (i < value.length) {
    if (value[i] === "{") {
      const close = value.indexOf("}", i);
      if (close !== -1) {
        const content = value.slice(i + 1, close);
        if (content.startsWith("/")) {
          i = close + 1;
          continue;
        }
        const hex = ALL_COLOR_CODES[content] ?? ALL_COLOR_CODES[content.toLowerCase()];
        if (hex) {
          flushText();
          nodes.push(
            <Box
              key={`c${key++}`}
              aria-label={`color ${content}`}
              className="inline-block align-middle h-3 w-3 rounded-sm border border-border/40"
              style={{ backgroundColor: hex }}
            />,
          );
          i = close + 1;
          continue;
        }
      }
    }
    textBuf += value[i];
    i++;
  }
  flushText();
  return nodes;
}

interface InstalledPluginRowProps {
  plugin: PluginInfo;
  onToggle: (pluginId: string, enabled: boolean) => void;
  isToggling: boolean;
  onConfigUpdate: () => void;
  onUninstall?: (pluginId: string) => void;
  onUpdate?: (pluginId: string) => void;
  isUninstalling?: boolean;
  isUpdating?: boolean;
  fullPage?: boolean;
  registryEntry?: RegistryEntry;
  connection?: OAuthConnection;
  desktop?: boolean;
  selected?: boolean;
  onSelect?: (id: string) => void;
  detailTarget?: HTMLElement | null;
}

/**
 * The state every transition plugin is in: deprecated (plan D22). Existing
 * `plugin:<id>` transitions keep running; removal of the plugin kind is under
 * consideration for v11. A state, so a badge, and it carries no data.
 */
function DeprecatedBadge({ label }: { label: string }) {
  return (
    <Badge variant="secondary" className="text-[10px] gap-1 px-1.5 py-0 h-5">
      <AlertCircle className="h-2.5 w-2.5" />
      {label}
    </Badge>
  );
}

type SortDir = "asc" | "desc";

/**
 * Keyboard-operable sorting for grouped rows and compact results (#2003).
 * The pressed button announces its localized direction; chevrons are decorative.
 */
function SortHeaderButton({
  label,
  active,
  dir,
  onSort,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onSort: () => void;
}) {
  const t = useTranslations("integrations");
  return (
    <button
      type="button"
      onClick={onSort}
      aria-pressed={active}
      aria-label={active ? `${label}, ${t(dir === "asc" ? "sortAscending" : "sortDescending")}` : label}
      // The kit's touch floor: 44 px on a coarse pointer (BB-C-26 app half).
      className="flex items-center gap-1 rounded-sm text-left font-medium cursor-pointer select-none hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring coarse:min-h-touch"
    >
      {label}
      {active ? (
        dir === "asc" ? (
          <ChevronUp className="h-3 w-3" aria-hidden="true" />
        ) : (
          <ChevronDown className="h-3 w-3" aria-hidden="true" />
        )
      ) : (
        <ChevronsUp className="h-3 w-3 opacity-30" aria-hidden="true" />
      )}
    </button>
  );
}

/**
 * Asks before an integration's page is left with edits that were not saved
 * (BB-C-18). Rendered only on the full-page route inside a data router; the
 * desktop list-detail pane and jsdom tests without one have no blocker.
 */
function UnsavedSettingsGuard({ dirty, leaving }: { dirty: boolean; leaving: RefObject<boolean> }) {
  const t = useTranslations("integrations");
  // `leaving` is set just before a deliberate exit (Save Changes, a guided
  // sign-in leaving for the provider, Uninstall), in the same tick as the
  // state that clears `dirty` — too soon for this render to see it.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && !leaving.current && currentLocation.pathname !== nextLocation.pathname,
  );
  useBeforeUnload(
    useCallback(
      (event: BeforeUnloadEvent) => {
        if (!dirty || leaving.current) return;
        event.preventDefault();
        event.returnValue = "";
      },
      [dirty, leaving],
    ),
  );
  return (
    <AlertDialog
      open={blocker.state === "blocked"}
      onOpenChange={(open) => {
        if (!open && blocker.state === "blocked") blocker.reset();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("discardChangesTitle")}</AlertDialogTitle>
          <AlertDialogDescription>{t("discardChangesDescription")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("keepEditing")}</AlertDialogCancel>
          <Button
            onClick={() => {
              if (blocker.state === "blocked") blocker.proceed();
            }}
          >
            {t("discardAndLeave")}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function InstalledPluginRow({
  plugin,
  onToggle,
  isToggling,
  onConfigUpdate,
  onUninstall,
  onUpdate,
  isUninstalling,
  isUpdating,
  fullPage = false,
  registryEntry,
  connection,
  desktop = false,
  selected = false,
  onSelect,
  detailTarget,
}: InstalledPluginRowProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [detailTab, setDetailTab] = useState(() => {
    if (!fullPage) return "settings";
    const tab = searchParams.get("tab");
    return tab === "variables" || tab === "readme" ? tab : "settings";
  });
  const isConfigOpen = fullPage || (desktop && selected);
  const setIsConfigOpen = (open: boolean) => {
    if (fullPage && !open) router.push("/integrations?tab=installed");
    else onSelect?.(open ? plugin.id : "");
  };
  const [configValues, setConfigValues] = useState<Record<string, unknown>>({});
  // What the form held when it loaded or last saved: edits are the difference.
  const [savedValues, setSavedValues] = useState<Record<string, unknown>>({});
  // The hub's reasons for refusing the last save, per field and otherwise.
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const hasDataRouter = useContext(UNSAFE_DataRouterContext) != null;
  // Set before a deliberate exit so the guard lets it through; any new edit
  // re-arms the guard.
  const leaving = useRef(false);
  const [isCreatingDemo, setIsCreatingDemo] = useState(false);
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
  const [showAddInstance, setShowAddInstance] = useState(false);
  const [instanceLabel, setInstanceLabel] = useState("");
  const [isCreatingInstance, setIsCreatingInstance] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const queryClient = useQueryClient();
  const t = useTranslations("integrations");
  const tCommon = useTranslations("common");
  const categoryLabels = useCategoryLabels();

  const isExternal = plugin.source?.source_type !== "builtin";
  // A first-party output (Vestaboard, FiestaPanel) updates here like any
  // plugin, but FiestaBoard needs it: the server refuses to uninstall it.
  const canUninstall = isExternal && plugin.required !== true;
  const hasUpdate = plugin.update_available === true;
  const isInstance = !!plugin.instance_label;
  // Transitions have no polling loop, so `PluginRegistry.get_transition_plugin()`
  // runs any installed one whether or not it is "enabled". Offering a toggle
  // here would promise control the backend does not honour, so the row shows a
  // type badge instead of a switch and instead of an enabled/disabled status.
  const isTransition = plugin.plugin_type === "transition";
  // An output plugin drives a board that names it; "enabled" means nothing
  // for it either, so it gets the same treatment: a type badge, no toggle.
  const isOutput = plugin.plugin_type === "output";
  const hasNoToggle = isTransition || isOutput;
  const needsReconnect = plugin.enabled && connection?.status === "reauthorization_required";
  const needsSetup = plugin.enabled && !hasNoToggle && !plugin.configured;
  const rowStatus = needsReconnect || needsSetup ? "warning" : hasNoToggle || !plugin.enabled ? "neutral" : "success";

  // Fetch plugin details when opening config
  const { data: pluginDetails, isLoading: isLoadingDetails } = useQuery({
    queryKey: ["plugin", plugin.id],
    queryFn: () => api.getPlugin(plugin.id),
    enabled: isConfigOpen,
  });

  // Fetch current variable values (the plugin's raw data) for the Template
  // Variables table. Polls while the sheet is open so users can watch values
  // update during troubleshooting. Reads GET /v1/plugins/{id}/data, the
  // successor of the deprecated GET /displays/{type}/raw (#1911).
  const {
    data: pluginData,
    isLoading: isLoadingPluginData,
    isFetching: isFetchingPluginData,
  } = useQuery({
    queryKey: ["plugin-data", plugin.id],
    queryFn: () => api.getPluginData(plugin.id),
    enabled: isConfigOpen && plugin.enabled,
    refetchInterval: 15_000,
  });

  // Initialize config values when plugin details load. Seed schema defaults
  // for any keys the saved config doesn't already set, so fields with a
  // declared `default` (e.g. refresh_seconds) show their value instead of
  // appearing blank. Saved config always wins over defaults.
  // `settings_schema` is raw manifest JSON on the wire; narrow it once here
  // so both the defaults seeding below and <SchemaForm> read the same shape.
  const settingsSchema = useMemo(() => asJSONSchema(pluginDetails?.settings_schema), [pluginDetails]);

  // Done during render rather than in an effect, so the config dialog's fields
  // are populated in its first commit instead of flashing empty
  // (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([pluginDetails]) && pluginDetails) {
    const defaults: Record<string, unknown> = {};
    for (const [key, prop] of Object.entries(settingsSchema.properties)) {
      if (prop && prop.default !== undefined) {
        defaults[key] = prop.default;
      }
    }
    const loaded = { ...defaults, ...(pluginDetails.config ?? {}) };
    setConfigValues(loaded);
    setSavedValues(loaded);
  }
  const isDirty = JSON.stringify(configValues) !== JSON.stringify(savedValues);

  // An edit to a field the hub refused clears that field's message.
  const updateConfigValues = (next: Record<string, unknown>) => {
    leaving.current = false;
    setConfigValues(next);
    setSaveError(null);
    setFieldErrors((current) => {
      const kept = Object.fromEntries(
        Object.entries(current).filter(([key]) => JSON.stringify(next[key]) === JSON.stringify(configValues[key])),
      );
      return Object.keys(kept).length === Object.keys(current).length ? current : kept;
    });
  };

  // A plugin whose users bring their own OAuth app has its Client ID (and
  // secret) fields inside the Account connection panel's guided setup, not in
  // the general settings form. Same query key as the panel, so one request.
  const { data: oauthConnections } = useQuery({
    queryKey: OAUTH_CONNECTIONS_QUERY_KEY,
    queryFn: api.listOAuthConnections,
    enabled: isConfigOpen,
  });
  const oauthFieldKeys = useMemo(
    () => oauthAppFieldKeys(findOAuthConnection(oauthConnections?.connections, plugin.id)),
    [oauthConnections, plugin.id],
  );
  const formSchema = useMemo(() => {
    if (oauthFieldKeys.length === 0) return settingsSchema;
    const properties = Object.fromEntries(
      Object.entries(settingsSchema.properties).filter(([key]) => !oauthFieldKeys.includes(key)),
    );
    return { ...settingsSchema, properties };
  }, [settingsSchema, oauthFieldKeys]);

  // The guided setup's sign-in button saves first, so the Client ID just
  // typed is the one the sign-in uses. Unlike Save Changes it keeps the sheet
  // open and lets the caller report a failure.
  const saveConfigForSignIn = async () => {
    await api.updatePluginConfig(plugin.id, configValues);
    // Saved, and the sign-in is about to leave for the provider.
    setSavedValues(configValues);
    leaving.current = true;
    onConfigUpdate();
    queryClient.invalidateQueries({ queryKey: ["plugin", plugin.id] });
    queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
  };
  const repositoryUrl = plugin.source?.repository_url?.replace(/\.git$/, "");
  const setupGuideUrl = repositoryUrl?.startsWith("https://github.com/")
    ? `${repositoryUrl}/blob/HEAD/docs/SETUP.md`
    : undefined;

  const handleSaveConfig = async () => {
    setIsSaving(true);
    setFieldErrors({});
    setSaveError(null);
    try {
      await api.updatePluginConfig(plugin.id, configValues);
      // Saved: leaving now must not ask about the edits just written.
      setSavedValues(configValues);
      leaving.current = true;
      toast.success(t("toastConfigSaved", { pluginName: plugin.name }));
      onConfigUpdate();
      // The sheet's own details query. Without this the panel keeps serving the
      // pre-save config for staleTime (1 min), so areDemoRequirementsMet() still
      // reads the old values and Create Demo Page stays disabled after a save
      // that actually satisfied the requirements.
      queryClient.invalidateQueries({ queryKey: ["plugin", plugin.id] });
      // A saved client ID is what makes an OAuth plugin connectable.
      queryClient.invalidateQueries({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-data", plugin.id] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      setIsConfigOpen(false);
    } catch (error) {
      // Said beside Save, not in a toast that lands on top of it (BB-C-18).
      const messages = pluginConfigErrors(error);
      if (!messages) {
        setSaveError(
          t("toastConfigSaveFailed", { error: error instanceof Error ? error.message : tCommon("unknownError") }),
        );
        return;
      }
      const mapped = mapConfigErrors(messages, formSchema.properties);
      setFieldErrors(mapped.fields);
      setSaveError([t("saveFieldErrors"), ...mapped.general].join(" "));
      const first = Object.keys(formSchema.properties).find((key) => mapped.fields[key]);
      if (first) {
        requestAnimationFrame(() => {
          const target = document.getElementById(first) ?? document.getElementById(`${first}-0`);
          target?.focus();
        });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateDemoPage = async () => {
    setIsCreatingDemo(true);
    try {
      const result = await api.createPluginDemoPage(plugin.id);
      const verb = result.recreated ? "recreated" : "created";
      toast.success(`Demo page ${verb} for ${plugin.name}`);
      queryClient.invalidateQueries({ queryKey: ["plugin", plugin.id] });
      queryClient.invalidateQueries({ queryKey: ["pages"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      setShowDemoConfirm(false);
    } catch (error) {
      toast.error(`Failed to create demo page: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setIsCreatingDemo(false);
    }
  };

  // Confirm a copied template variable
  const handleVarCopied = (templateVar: string) => {
    toast.success(`Copied ${templateVar}`);
  };

  const areDemoRequirementsMet = (): boolean => {
    if (!pluginDetails?.settings_schema) return true;
    const schema = pluginDetails.settings_schema as {
      required?: string[];
      properties?: Record<string, { type?: string }>;
    };
    const required = schema.required ?? [];
    const config = pluginDetails.config ?? {};
    return required.every((field) => field === "enabled" || Boolean(config[field]));
  };

  // Flatten the plugin's manifest variables into table rows, then read the
  // declared groups so the table can be organized the same way the page-builder
  // variable picker organizes them.
  const variablesBlock = pluginDetails?.variables as VariablesBlock | undefined;
  const variableRows = buildVariablesList(variablesBlock, pluginDetails?.max_lengths);
  const variableGroups = getVariableGroups(variablesBlock);
  const hasVariableGroups = Object.keys(variableGroups).length > 0;

  // Render one Template Variables row. Shared by the flat and grouped layouts so
  // the two stay identical.
  const renderVariableRow = (variable: PluginVariableRow) => {
    const resolved = formatCurrentValue(
      variable.name,
      pluginData?.available ? (pluginData.data as Record<string, unknown>) : undefined,
    );
    return (
      <TableRow key={variable.name} className="hover:bg-muted/30 transition-colors">
        <TableCell className="px-3 py-2 align-top">
          <CopyableCode
            value={`{{${plugin.id}.${variable.name}}}`}
            onCopied={handleVarCopied}
            className="text-primary bg-primary/10 hover:bg-primary/20"
          >
            {plugin.id}.{variable.name}
          </CopyableCode>
        </TableCell>
        <TableCell className="px-3 py-2 text-muted-foreground capitalize align-top">{variable.description}</TableCell>
        <TableCell className="px-3 py-2 align-top max-w-[200px]">
          {!plugin.enabled ? (
            <Text as="span" tone="muted">
              —
            </Text>
          ) : isLoadingPluginData ? (
            <Skeleton className="h-3 w-16" />
          ) : pluginData && pluginData.available === false ? (
            <Text as="span" tone="muted" className="italic">
              {t("valueUnavailable")}
            </Text>
          ) : resolved && resolved.short !== "" ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Flex align="center" gap="1" className="truncate font-mono text-[11px]">
                  {renderValueWithColors(resolved.short)}
                </Flex>
              </TooltipTrigger>
              <TooltipContent
                side="top"
                className="max-w-[360px] whitespace-pre-wrap break-words font-mono text-[11px]"
              >
                <Flex inline wrap align="center" gap="1">
                  {renderValueWithColors(resolved.full)}
                </Flex>
              </TooltipContent>
            </Tooltip>
          ) : (
            <Text as="span" tone="muted">
              —
            </Text>
          )}
        </TableCell>
        <TableCell className="px-3 py-2 text-center align-top">
          <Badge variant="outline" className="text-[10px]">
            {variable.maxChars}
          </Badge>
        </TableCell>
      </TableRow>
    );
  };

  // Use icon from plugin manifest, falling back to Puzzle
  const Icon = ICON_MAP[normalizePluginIconKey(plugin.icon)] ?? Puzzle;

  const categoryLabel = categoryLabels[plugin.category || "utility"] || plugin.category || categoryLabels.utility;

  function handleCreateInstance() {
    if (!instanceLabel.trim()) return;
    setIsCreatingInstance(true);
    const baseId = plugin.base_plugin_id ?? plugin.id;
    api
      .createPluginInstance(baseId, instanceLabel.trim())
      .then(() => {
        toast.success(`Instance "${instanceLabel}" created for ${plugin.name}`);
        queryClient.invalidateQueries({ queryKey: ["plugins"] });
        setShowAddInstance(false);
        setInstanceLabel("");
      })
      .catch((err) => {
        toast.error(`Failed to create instance: ${err instanceof Error ? err.message : "Unknown error"}`);
      })
      .finally(() => {
        setIsCreatingInstance(false);
      });
  }

  async function handleDeleteInstance() {
    const baseId = plugin.base_plugin_id ?? plugin.id.split(":")[0];
    const label = plugin.instance_label ?? "";
    try {
      await api.deletePluginInstance(baseId, label);
      toast.success(`Instance "${label}" deleted`);
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      if (fullPage) router.push("/integrations?tab=installed");
    } catch (err) {
      toast.error(`Failed to delete instance: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setShowDeleteConfirm(false);
    }
  }

  // One supported detail body: the same schema, OAuth, variables, colors and
  // mutation state serve the selected desktop pane and installed detail route.
  const badges = (
    <Flex gap="2" align="center" wrap className={fullPage ? undefined : "mt-3"}>
      <Badge variant="outline">{tCommon("versionShort", { version: plugin.version })}</Badge>
      <PluginProvenance repository={plugin.source?.repository_url} />
      <Badge variant="outline">
        {t(
          plugin.source?.source_type === "builtin"
            ? "sourceCoreBadge"
            : plugin.source?.source_type === "git"
              ? "sourceExternalBadge"
              : "sourceMarketplaceBadge",
        )}
      </Badge>
    </Flex>
  );
  const configContent = (
    <>
      {/* On its own page the badges share the switch's row (BB-C-21). */}
      {!fullPage && badges}
      <Tabs
        value={detailTab}
        onValueChange={(value) => {
          if (!fullPage && value === "readme") {
            router.push(`/integrations/${encodeURIComponent(plugin.id)}?from=installed&tab=readme`);
            return;
          }
          setDetailTab(value);
          if (fullPage)
            router.replace(`/integrations/${encodeURIComponent(plugin.id)}?from=installed&tab=${value}`, {
              scroll: false,
            });
        }}
      >
        <TabsList aria-label={t("detailTabs")} className="mt-4 max-w-full">
          <TabsTrigger value="settings">{t("settingsSection")}</TabsTrigger>
          <TabsTrigger value="variables">{t("variablesTab")}</TabsTrigger>
          <TabsTrigger value="readme">{t("readmeTab")}</TabsTrigger>
        </TabsList>
        <TabsContent value="settings">
          <IntegrationBoardPreview entry={registryEntry} size={fullPage ? undefined : "sm"} />
          <Stack gap="6" className="py-6">
            {isLoadingDetails ? (
              <Stack gap="4">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </Stack>
            ) : (
              <>
                {/* Demo Page Section */}
                {pluginDetails?.has_demo && (
                  <Stack gap="3" className="rounded-lg border bg-muted/30 p-4">
                    {/* The button wraps under the text when both don't fit, so a
                        long label (German) never squeezes the text to one word
                        per line (BB-C-21). */}
                    <Flex align="center" justify="between" gap="3" wrap>
                      <Box className="min-w-0 flex-1 basis-56">
                        <Heading level={4} size="sm" className="font-medium">
                          {t("demoPage.title")}
                        </Heading>
                        <Text size="xs" tone="muted" className="mt-0.5">
                          {pluginDetails.demo_page_id ? t("demoPage.alreadyExists") : t("demoPage.createDescription")}
                        </Text>
                      </Box>
                      {pluginDetails.demo_page_id ? (
                        <Dialog open={showDemoConfirm} onOpenChange={setShowDemoConfirm}>
                          <DialogTrigger asChild>
                            <Button variant="outline" size="sm" disabled={!areDemoRequirementsMet() || isCreatingDemo}>
                              <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                              {t("demoPage.recreateButton")}
                            </Button>
                          </DialogTrigger>
                          <DialogContent>
                            <DialogHeader>
                              <DialogTitle>{t("demoPage.recreateConfirmTitle")}</DialogTitle>
                              <DialogDescription>{t("demoPage.recreateConfirmDescription")}</DialogDescription>
                            </DialogHeader>
                            <DialogFooter>
                              <Button variant="outline" onClick={() => setShowDemoConfirm(false)}>
                                {tCommon("cancel")}
                              </Button>
                              <Button onClick={handleCreateDemoPage} disabled={isCreatingDemo}>
                                {isCreatingDemo ? t("demoPage.creating") : t("demoPage.recreateAction")}
                              </Button>
                            </DialogFooter>
                          </DialogContent>
                        </Dialog>
                      ) : (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={handleCreateDemoPage}
                          disabled={!areDemoRequirementsMet() || isCreatingDemo}
                        >
                          <Play className="h-3.5 w-3.5 mr-1.5" />
                          {isCreatingDemo ? t("demoPage.creating") : t("demoPage.createAction")}
                        </Button>
                      )}
                    </Flex>
                    {!areDemoRequirementsMet() && (
                      <Text size="xs" tone="warning">
                        {t("demoPage.requirementsWarning")}
                      </Text>
                    )}
                  </Stack>
                )}

                {/* Renders nothing unless the plugin's manifest declares OAuth. */}
                <OAuthConnectionSection
                  pluginId={plugin.id}
                  appFields={{
                    values: configValues,
                    onChange: (key, value) => {
                      leaving.current = false;
                      setConfigValues((current) => ({ ...current, [key]: value }));
                    },
                    save: saveConfigForSignIn,
                    setupGuideUrl,
                  }}
                />

                {/* Settings Section */}
                {Object.keys(formSchema.properties).length > 0 && (
                  <Stack gap="4">
                    <Heading level={4} size="sm" className="font-medium text-muted-foreground">
                      {t("settingsSection")}
                    </Heading>
                    <SchemaForm
                      schema={formSchema}
                      values={configValues}
                      onChange={updateConfigValues}
                      errors={fieldErrors}
                      disabled={isSaving}
                      // Lets `remote-options` fields ask this plugin — and only
                      // this plugin — for their catalogs.
                      pluginId={plugin.id}
                    />
                  </Stack>
                )}

                {/* Environment Variables Section */}
                {pluginDetails?.env_vars && pluginDetails.env_vars.length > 0 && (
                  <Stack gap="3">
                    <Heading level={4} size="sm" className="font-medium text-muted-foreground">
                      {t("environmentVariablesSection")}
                    </Heading>
                    <Box className="rounded-md border overflow-hidden">
                      <Table className="text-xs focus-ring" tabIndex={0} aria-label={t("environmentVariablesSection")}>
                        <TableHeader className="bg-muted/50">
                          <TableRow>
                            <TableHead className="text-left px-3 py-2 font-medium h-auto">
                              {t("variableColumn")}
                            </TableHead>
                            <TableHead className="text-left px-3 py-2 font-medium h-auto">
                              {t("descriptionColumn")}
                            </TableHead>
                            <TableHead className="text-center px-3 py-2 font-medium h-auto">
                              {t("requiredBadge")}
                            </TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody className="divide-y">
                          {pluginDetails.env_vars.map((envVar) => (
                            <TableRow key={envVar.name} className="hover:bg-muted/30">
                              <TableCell className="px-3 py-2">
                                <CodeChip>{envVar.name}</CodeChip>
                              </TableCell>
                              <TableCell className="px-3 py-2 text-muted-foreground">{envVar.description}</TableCell>
                              <TableCell className="px-3 py-2 text-center">
                                {envVar.required ? (
                                  <Badge variant="destructive" className="text-[10px]">
                                    {t("requiredBadge")}
                                  </Badge>
                                ) : (
                                  <Badge variant="outline" className="text-[10px]">
                                    {t("optionalBadge")}
                                  </Badge>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </Box>
                  </Stack>
                )}

                {/* Color Rules Section */}
                <ColorRulesEditor
                  pluginId={plugin.id}
                  colorRules={(configValues.color_rules as ColorRulesConfig) || {}}
                  onChange={(newRules) => updateConfigValues({ ...configValues, color_rules: newRules })}
                  onVarCopied={handleVarCopied}
                />

                {/* No config message */}
                {(!pluginDetails?.settings_schema ||
                  Object.keys(pluginDetails.settings_schema.properties || {}).length === 0) &&
                  variableRows.length === 0 && <Text tone="muted">{t("noConfigOptions")}</Text>}
              </>
            )}
          </Stack>
          {saveError && (
            <Alert variant="destructive" className="mb-3" data-testid="integration-save-error">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              <AlertDescription>{saveError}</AlertDescription>
            </Alert>
          )}
          <Flex gap="2" wrap className="justify-end">
            {canUninstall && onUninstall && (
              <Button
                variant="destructive"
                className="sm:mr-auto"
                size="sm"
                onClick={() => {
                  // Uninstalling discards the settings anyway: don't ask.
                  leaving.current = true;
                  setIsConfigOpen(false);
                  onUninstall(plugin.id);
                }}
                disabled={isUninstalling}
              >
                <Trash2 className="h-3.5 w-3.5 mr-1" />
                {isUninstalling ? "Uninstalling..." : "Uninstall"}
              </Button>
            )}
            <Button variant="outline" disabled={isSaving} onClick={() => setIsConfigOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button onClick={handleSaveConfig} disabled={isSaving || isLoadingDetails}>
              {isSaving ? tCommon("saving") : t("saveChanges")}
            </Button>
          </Flex>
        </TabsContent>
        <TabsContent value="variables" className="py-4 min-w-0 overflow-x-auto">
          {isLoadingDetails && <Skeleton className="h-24 w-full" />}
          {/* Template Variables Section */}
          {variableRows.length > 0 && (
            <TooltipProvider delayDuration={200}>
              <Stack gap="3">
                <Heading level={4} size="sm" className="font-medium text-muted-foreground">
                  {t("templateVariablesSection")}
                  <Text as="span" size="xs" tone="muted" className="ml-2">
                    ({t("templateVariablesClickToCopy")})
                  </Text>
                </Heading>
                {!plugin.enabled && (
                  <Text size="xs" tone="muted" className="italic">
                    {t("enablePluginForLiveValues")}
                  </Text>
                )}
                {plugin.enabled && pluginData && pluginData.available === false && (
                  <Text size="xs" tone="warning">
                    {pluginData.error
                      ? t("liveValuesUnavailableWithError", { error: pluginData.error })
                      : t("liveValuesUnavailable")}
                  </Text>
                )}
                <Box className="rounded-md border overflow-hidden">
                  <Table className="text-xs">
                    <TableHeader className="bg-muted/50">
                      <TableRow>
                        <TableHead className="text-left px-3 py-2 font-medium h-auto">{t("variableColumn")}</TableHead>
                        <TableHead className="text-left px-3 py-2 font-medium h-auto">
                          {t("descriptionColumn")}
                        </TableHead>
                        <TableHead className="text-left px-3 py-2 font-medium h-auto">
                          {t("currentValueColumn")}
                          {plugin.enabled && isFetchingPluginData && !isLoadingPluginData && (
                            <Text as="span" size="xs" tone="muted" className="ml-1.5 text-[10px] font-normal">
                              ({t("refreshingValues")})
                            </Text>
                          )}
                        </TableHead>
                        <TableHead className="text-center px-3 py-2 font-medium h-auto">{t("maxColumn")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody className="divide-y">
                      {hasVariableGroups
                        ? groupVariableRows(variableRows, variableGroups, "General").map((section) => (
                            <Fragment key={section.groupId ?? "__general__"}>
                              <TableRow className="bg-muted/40">
                                <TableHead
                                  scope="colgroup"
                                  colSpan={4}
                                  className="text-left px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground h-auto"
                                >
                                  {section.label}
                                </TableHead>
                              </TableRow>
                              {section.rows.map(renderVariableRow)}
                            </Fragment>
                          ))
                        : variableRows.map(renderVariableRow)}
                    </TableBody>
                  </Table>
                </Box>
                <Text size="xs" tone="muted">
                  {t.rich("useInTemplates", {
                    example: () => (
                      <CodeChip className="bg-muted px-1 py-0 rounded">{`{{${plugin.id}.variable}}`}</CodeChip>
                    ),
                  })}
                </Text>
              </Stack>
            </TooltipProvider>
          )}

          {!isLoadingDetails && variableRows.length === 0 && <Text tone="muted">{t("noVariables")}</Text>}
        </TabsContent>
        <TabsContent value="readme" className="py-4">
          <IntegrationReadme
            pluginId={plugin.id}
            repository={repositoryUrl}
            branch={registryEntry?.branch}
            documentation={pluginDetails?.documentation}
            version={plugin.version}
            author={pluginDetails?.author || plugin.author}
          />
        </TabsContent>
      </Tabs>
    </>
  );
  const detailContent = (
    <Stack gap="4" className="min-w-0">
      {/* On its own page the section's breadcrumb is the way back; a second
          Back link under it pushed the settings down a screen (BB-C-21). */}
      {(needsReconnect || needsSetup) && (
        <Alert variant="warning" data-testid="integration-attention-banner">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>
            {needsReconnect ? t("reconnectTitle", { name: plugin.name }) : t("setupRequiredBadge")}
          </AlertTitle>
          <AlertDescription>{needsReconnect ? t("reconnectConsequence") : t("setupConsequence")}</AlertDescription>
        </Alert>
      )}
      <Card
        className={cn(
          "min-w-0 overflow-x-auto",
          detailTab === "readme" ? "border-0 bg-transparent shadow-none p-0" : "p-5",
        )}
      >
        <Flex justify="between" align="center" gap="3" wrap>
          {fullPage ? (
            badges
          ) : (
            <Heading level={2} size="xl">
              {plugin.name}
            </Heading>
          )}
          <Flex align="center" justify="end" gap="0.5">
            {!hasNoToggle && (
              <Switch
                checked={plugin.enabled}
                onCheckedChange={(checked) => onToggle(plugin.id, checked)}
                disabled={isToggling}
                aria-label={t("toggleAriaLabel", { pluginName: plugin.name })}
              />
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t("moreOptionsAriaLabel")}>
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setDetailTab("settings")}>
                  <Settings className="h-3.5 w-3.5 mr-2" />
                  {t("configureButton")}
                </DropdownMenuItem>
                {!isInstance && (
                  <DropdownMenuItem onClick={() => setShowAddInstance(true)}>
                    <CopyPlus className="h-3.5 w-3.5 mr-2" />
                    {t("addInstanceAction")}
                  </DropdownMenuItem>
                )}
                {!hasNoToggle && (
                  <DropdownMenuItem onClick={() => onToggle(plugin.id, !plugin.enabled)} disabled={isToggling}>
                    {plugin.enabled ? (
                      <XCircle className="h-3.5 w-3.5 mr-2" />
                    ) : (
                      <CheckCircle className="h-3.5 w-3.5 mr-2" />
                    )}
                    {plugin.enabled ? "Disable" : "Enable"}
                  </DropdownMenuItem>
                )}
                {hasUpdate && onUpdate && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => onUpdate(plugin.id)} disabled={isUpdating}>
                      {isUpdating ? (
                        <Spinner size="sm" className="mr-2" label={null} />
                      ) : (
                        <RefreshCw className="h-3.5 w-3.5 mr-2" />
                      )}
                      {isUpdating ? "Updating..." : "Update"}
                    </DropdownMenuItem>
                  </>
                )}
                {isInstance && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => setShowDeleteConfirm(true)}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-2" />
                      {tCommon("delete")}
                    </DropdownMenuItem>
                  </>
                )}
                {canUninstall && onUninstall && !isInstance && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => setShowDeleteConfirm(true)}
                      disabled={isUninstalling}
                      className="text-destructive focus:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-2" />
                      {isUninstalling ? "Uninstalling..." : "Delete"}
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </Flex>
        </Flex>
        {showAddInstance && (
          <Box role="group" aria-label={t("addInstanceAction")} className="rounded-lg border p-4">
            <Box>
              <Flex align="center" gap="3" className="max-w-md">
                <Label htmlFor={`instance-label-${plugin.id}`} className="text-sm whitespace-nowrap">
                  {t("instanceNameInlineLabel")}
                </Label>
                <Input
                  id={`instance-label-${plugin.id}`}
                  placeholder="e.g. sf, prod, api-2"
                  value={instanceLabel}
                  onChange={(e) => setInstanceLabel(e.target.value)}
                  className="h-8 text-sm"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && instanceLabel.trim()) {
                      handleCreateInstance();
                    }
                    if (e.key === "Escape") {
                      setShowAddInstance(false);
                      setInstanceLabel("");
                    }
                  }}
                />
                <Button
                  size="sm"
                  className="h-8"
                  disabled={!instanceLabel.trim() || isCreatingInstance}
                  onClick={handleCreateInstance}
                >
                  {isCreatingInstance ? "Creating..." : "Create"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-8"
                  onClick={() => {
                    setShowAddInstance(false);
                    setInstanceLabel("");
                  }}
                >
                  {tCommon("cancel")}
                </Button>
              </Flex>
              <Text size="xs" tone="muted" className="mt-1.5">
                {t("addInstanceInlineHelp")}
              </Text>
            </Box>
          </Box>
        )}
        {configContent}
      </Card>
      {fullPage && hasDataRouter && <UnsavedSettingsGuard dirty={isDirty} leaving={leaving} />}
    </Stack>
  );
  const configPanel = isConfigOpen && detailTarget ? createPortal(detailContent, detailTarget) : null;
  const row = (
    // ListRowItem, not ListItem: it tells the kit's ListRow it is already
    // in an item, so the row doesn't wrap itself in a second <li>.
    <ListRowItem>
      <ListRow
        {...anchorProps(`plugin.${plugin.id}`)}
        data-section-item={plugin.id}
        selected={desktop && selected}
        render={
          desktop ? (
            <button type="button" onClick={() => setIsConfigOpen(true)} />
          ) : (
            <Link href={`/integrations/${encodeURIComponent(plugin.id)}?from=installed`} />
          )
        }
        leading={
          desktop ? (
            <IconTile size="sm" tone="muted">
              <Icon className="h-4 w-4" />
            </IconTile>
          ) : (
            // A phone row leads with its state, as in Figma 324:50158; the
            // status line beside it says the same in words.
            <StatusDot status={rowStatus} size="md" className="mx-1" />
          )
        }
        title={plugin.name}
        description={
          <>
            {isTransition ? (
              <>
                <Text as="span">{t("transitionBadge")}</Text> · <DeprecatedBadge label={t("deprecatedBadge")} />
              </>
            ) : isOutput ? (
              t("outputBadge")
            ) : needsReconnect ? (
              t("oauth.statusReconnect")
            ) : !plugin.enabled ? (
              t("disabledBadge")
            ) : needsSetup ? (
              t("setupRequiredBadge")
            ) : (
              t("configuredBadge")
            )}
            <Text as="span" className="sr-only">
              {categoryLabel}
            </Text>
            {hasUpdate && (
              <Badge variant="outline" className="ml-2">
                {t("updateAvailableBadge")}
              </Badge>
            )}
          </>
        }
        trailing={
          <>
            {(needsReconnect || needsSetup) && (
              <Text as="span" className="text-brand">
                {needsReconnect ? t("oauth.reconnectButton") : t("setUpAction")}
              </Text>
            )}
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </>
        }
      />
    </ListRowItem>
  );

  // Delete / uninstall confirmation dialog
  const deleteConfirmDialog = showDeleteConfirm && (
    <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
      <AlertDialogContent>
        <AlertDialogHeader>
          {isInstance ? (
            <AlertDialogTitle>{t("deleteInstanceConfirmTitle", { label: plugin.instance_label })}</AlertDialogTitle>
          ) : (
            <AlertDialogTitle>{t("deletePluginConfirmTitle", { name: plugin.name })}</AlertDialogTitle>
          )}
          <AlertDialogDescription>
            {isInstance ? t("deleteInstanceConfirmDescription") : t("deletePluginConfirmDescription")}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={
              isInstance
                ? handleDeleteInstance
                : () => {
                    setShowDeleteConfirm(false);
                    onUninstall?.(plugin.id);
                  }
            }
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {tCommon("delete")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return (
    <>
      {fullPage ? (
        detailContent
      ) : (
        <>
          {row}
          {configPanel}
        </>
      )}
      {deleteConfirmDialog}
    </>
  );
}

/**
 * Marketplace card, built on the design system's `PluginCard` so it reads the
 * same as the public plugin directory at fiestaboard.app/plugins — including
 * the split-flap teaser strip, which is the whole point: you can see what a
 * plugin puts on a board before installing it. The board color is the user's
 * own, not a guess from the UI theme.
 */
function RegistryPluginCard({
  entry,
  onInstall,
  isInstalling,
  isInstalled = false,
  index = 0,
  compact = false,
}: {
  entry: RegistryEntry;
  onInstall: (pluginId: string) => void;
  isInstalling: boolean;
  isInstalled?: boolean;
  index?: number;
  compact?: boolean;
}) {
  const t = useTranslations("integrations");
  const boardColor = useEffectiveBoardColor();
  const code62Glyph = useEffectiveCode62Glyph();
  const categoryLabels = useCategoryLabels();
  const Icon = ICON_MAP[normalizePluginIconKey(entry.icon)] ?? Puzzle;

  return (
    <Box {...anchorProps(`plugin.${entry.id}`)}>
      <PluginCard
        variant={compact ? "compact" : "card"}
        icon={<Icon className="h-5 w-5" />}
        category={compact ? entry.category : undefined}
        categoryLabel={categoryLabels[entry.category] || entry.category}
        className="animate-card-fade-in"
        style={{ animationDelay: `${index * 60}ms` }}
        name={entry.name}
        description={
          <>
            {entry.description}
            {entry.plugin_type === "output" && <Badge variant="outline">{t("outputBadge")}</Badge>}
            {entry.plugin_type === "transition" && (
              <>
                <Badge variant="outline">{t("transitionBadge")}</Badge>
                <DeprecatedBadge label={t("deprecatedBadge")} />
              </>
            )}
          </>
        }
        authorLabel={
          <Text as="span" className="inline-flex flex-wrap items-center gap-2">
            {t("byAuthor", { author: entry.author })}
            <PluginProvenance repository={entry.repository} />
            {compact && (
              <Text as="span" size="xs" tone="muted">
                {entry.added
                  ? new Date(`${entry.added}T00:00:00`).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })
                  : "—"}
              </Text>
            )}
          </Text>
        }
        teaser={entry.teaser}
        boardType={boardColor}
        code62Glyph={code62Glyph}
        renderLink={({ className, children }) => (
          <Link href={`/integrations/${entry.id}`} className={className}>
            {children}
          </Link>
        )}
        action={
          isInstalled ? (
            <Badge variant="secondary" className="text-xs gap-1">
              <CheckCircle className="h-3 w-3" />
              {t("installedBadge")}
            </Badge>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-xs"
              onClick={() => onInstall(entry.id)}
              disabled={isInstalling}
            >
              {isInstalling ? (
                <Spinner label={null} className="h-3 w-3 mr-1" />
              ) : (
                <ArrowDownToLine className="h-3 w-3 mr-1" aria-hidden="true" />
              )}
              {isInstalling ? t("installing") : t("installAction")}
            </Button>
          )
        }
      />
    </Box>
  );
}

export function useInstalledPluginActions() {
  const t = useTranslations("integrations");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const data = queryClient.getQueryData<import("@/lib/api").PluginsListResponse>(["plugins"]);
  const [uninstallingId, setUninstallingId] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  // Toggle plugin mutation
  const toggleMutation = useMutation({
    mutationFn: async ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) => {
      if (enabled) {
        return api.enablePlugin(pluginId);
      } else {
        return api.disablePlugin(pluginId);
      }
    },
    onMutate: async ({ pluginId, enabled }) => {
      await queryClient.cancelQueries({ queryKey: ["plugins"] });
      const previousPlugins = queryClient.getQueryData(["plugins"]);
      queryClient.setQueryData(["plugins"], (old: typeof data) => {
        if (!old) return old;
        return {
          ...old,
          plugins: old.plugins.map((p: PluginInfo) => (p.id === pluginId ? { ...p, enabled } : p)),
          enabled_count: enabled ? old.enabled_count + 1 : old.enabled_count - 1,
        };
      });
      return { previousPlugins };
    },
    onError: (err, { pluginId }, context) => {
      queryClient.setQueryData(["plugins"], context?.previousPlugins);
      toast.error(t("toastToggleFailed", { pluginId, error: err instanceof Error ? err.message : tCommon("error") }));
    },
    onSuccess: (_, { pluginId, enabled }) => {
      toast.success(
        t("toastToggleSuccess", {
          pluginId,
          state: enabled ? tCommon("enabled").toLowerCase() : tCommon("disabled").toLowerCase(),
        }),
      );
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["plugins"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["template-variables"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"], refetchType: "active" });
    },
  });

  const handleToggle = (pluginId: string, enabled: boolean) => {
    toggleMutation.mutate({ pluginId, enabled });
  };

  const handleUninstall = async (pluginId: string) => {
    setUninstallingId(pluginId);
    try {
      await api.uninstallPlugin(pluginId);
      toast.success(t("toastUninstalled", { pluginId }));
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      return true;
    } catch (err) {
      toast.error(
        t("toastUninstallFailed", { pluginId, error: err instanceof Error ? err.message : tCommon("error") }),
      );
      return false;
    } finally {
      setUninstallingId(null);
    }
  };

  const handleUpdate = async (pluginId: string) => {
    setUpdatingId(pluginId);
    try {
      await api.updatePlugin(pluginId);
      toast.success(t("toastUpdated", { pluginId }));
      queryClient.invalidateQueries({ queryKey: ["plugin", pluginId] });
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
    } catch (err) {
      toast.error(t("toastUpdateFailed", { pluginId, error: err instanceof Error ? err.message : tCommon("error") }));
    } finally {
      setUpdatingId(null);
    }
  };

  return { toggleMutation, handleToggle, handleUninstall, handleUpdate, uninstallingId, updatingId };
}

export default function IntegrationsPage() {
  const t = useTranslations("integrations");
  const tCommon = useTranslations("common");
  const categoryLabels = useCategoryLabels();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const router = useRouter();
  const tOAuth = useTranslations("integrations.oauth");
  // An OAuth sign-in lands back here with its outcome in the query string
  // (src/oauth/routes.py). Read once, report it, then clean the URL so a
  // reload does not report it again.
  const [oauthReturn] = useState(() => readOAuthReturn(searchParams));
  const oauthReturnReported = useRef(false);
  useEffect(() => {
    if (!oauthReturn || oauthReturnReported.current) return;
    oauthReturnReported.current = true;
    if (oauthReturn.outcome === "connected") {
      toast.success(tOAuth("toastConnected"));
    } else {
      toast.error(tOAuth(oauthReturnErrorKey(oauthReturn.reason)));
    }
    router.replace(
      oauthReturn.pluginId
        ? `/integrations/${encodeURIComponent(oauthReturn.pluginId)}?from=installed`
        : "/integrations?tab=installed",
      { scroll: false },
    );
  }, [oauthReturn, router, tOAuth]);
  const [activeTab, setActiveTab] = useState(() => {
    const tab = searchParams.get("tab");
    return tab === "marketplace" || tab === "installed" ? tab : "installed";
  });
  const [marketplaceView, setMarketplaceView] = useState<"card" | "list">("card");
  const [marketplaceSort, setMarketplaceSort] = useState<{
    key: "name" | "category" | "author" | "added";
    dir: "asc" | "desc";
  }>({
    key: "name",
    dir: "asc",
  });
  const [installedSort, setInstalledSort] = useState<{ key: "name" | "category" | "status"; dir: "asc" | "desc" }>({
    key: "name",
    dir: "asc",
  });
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [isUpdatingAll, setIsUpdatingAll] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [marketplacePage, setMarketplacePage] = useState(0);
  const [gitDialogOpen, setGitDialogOpen] = useState(false);
  const gitInstall = useGitPluginInstall();
  const desktop = useMediaQuery("(min-width: 768px)");
  const phone = useMediaQuery("(max-width: 767px)");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailTarget, setDetailTarget] = useState<HTMLElement | null>(null);
  const { data: connections } = useQuery({
    queryKey: OAUTH_CONNECTIONS_QUERY_KEY,
    queryFn: api.listOAuthConnections,
  });

  // Fetch installed plugins list
  const { data, isLoading, error } = useQuery({
    queryKey: ["plugins"],
    queryFn: api.listPlugins,
  });

  // Fetch registry (available but not necessarily installed)
  const { data: registryData } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: api.listRegistryPlugins,
    staleTime: 5 * 60 * 1000,
  });

  const { toggleMutation, handleToggle, handleUninstall, handleUpdate, uninstallingId, updatingId } =
    useInstalledPluginActions();

  const handleInstall = async (pluginId: string) => {
    setInstallingId(pluginId);
    try {
      await api.installRegistryPlugin(pluginId);
      await api.enablePlugin(pluginId);
      toast.success(t("toastInstalledAndEnabled", { pluginId }));
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      setActiveTab("installed");
    } catch (err) {
      toast.error(t("toastInstallFailed", { pluginId, error: err instanceof Error ? err.message : tCommon("error") }));
    } finally {
      setInstallingId(null);
    }
  };

  const handleUpdateAll = async () => {
    setIsUpdatingAll(true);
    try {
      const result = await api.applyAllPluginUpdates();
      if (result.updated.length > 0) {
        toast.success(t("toastUpdateAllSuccess", { count: result.updated.length }));
      }
      const failedIds = Object.keys(result.failed);
      if (failedIds.length > 0) {
        toast.error(t("toastUpdateAllPartialFail", { count: failedIds.length, ids: failedIds.join(", ") }));
      }
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
    } catch (err) {
      toast.error(t("toastUpdateAllFailed", { error: err instanceof Error ? err.message : tCommon("error") }));
    } finally {
      setIsUpdatingAll(false);
    }
  };

  const handleInstallFromGit = async () => {
    if (!gitInstall.canInstall) return;
    try {
      const pluginId = await gitInstall.install();
      toast.success(t("toastInstalledFromGit", { pluginId }));
      setGitDialogOpen(false);
      setActiveTab("installed");
      gitInstall.reset();
    } catch (err) {
      toast.error(t("toastInstallFromGitFailed", { error: err instanceof Error ? err.message : tCommon("error") }));
    }
  };

  // Build a merged view: all registry entries, marking which are installed
  const installedIds = new Set(data?.plugins.map((p) => p.base_plugin_id ?? p.id) ?? []);
  const allRegistryEntries = registryData?.entries ?? [];

  const query = searchQuery.toLowerCase().trim();

  // A phone shows no search on Installed (Figma 324:50158), so a query typed
  // on Marketplace must not silently filter it.
  const installedQuery = phone ? "" : query;
  const filteredInstalled = (data?.plugins ?? []).filter(
    (p) =>
      !installedQuery ||
      p.name.toLowerCase().includes(installedQuery) ||
      p.description?.toLowerCase().includes(installedQuery) ||
      p.id.toLowerCase().includes(installedQuery),
  );

  const filteredRegistry = allRegistryEntries.filter(
    (e) =>
      (categoryFilter === "all" || (e.category || "utility") === categoryFilter) &&
      (!query ||
        e.name.toLowerCase().includes(query) ||
        e.description?.toLowerCase().includes(query) ||
        e.id.toLowerCase().includes(query)),
  );

  const availableCount = allRegistryEntries.length;

  // Sorted flat list for marketplace list view
  const sortedRegistry = [...filteredRegistry].sort((a, b) => {
    let valA = "";
    let valB = "";
    if (marketplaceSort.key === "name") {
      valA = a.name;
      valB = b.name;
    } else if (marketplaceSort.key === "category") {
      valA = categoryLabels[a.category || "utility"] || a.category || "";
      valB = categoryLabels[b.category || "utility"] || b.category || "";
    } else if (marketplaceSort.key === "author") {
      valA = a.author || "";
      valB = b.author || "";
    } else if (marketplaceSort.key === "added") {
      // ISO dates sort correctly as strings. Entries with no date go last in
      // both directions -- an unknown date is not "the oldest", and letting
      // "" sort first would bury the newest plugins under it. Same-day
      // entries (a bulk extraction publishes many at once) fall back to name
      // so the order is stable rather than incidental.
      const dateA = a.added || "";
      const dateB = b.added || "";
      if (dateA !== dateB) {
        if (!dateA) return 1;
        if (!dateB) return -1;
        return marketplaceSort.dir === "asc" ? dateA.localeCompare(dateB) : dateB.localeCompare(dateA);
      }
      return a.name.localeCompare(b.name);
    }
    return marketplaceSort.dir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
  });

  const resultPages = Math.max(1, Math.ceil(sortedRegistry.length / 12));
  const currentMarketplacePage = Math.min(marketplacePage, resultPages - 1);
  const visibleRegistry = sortedRegistry.slice(currentMarketplacePage * 12, currentMarketplacePage * 12 + 12);
  // Group all registry entries by category (for Marketplace tab card view)
  const groupedRegistry = visibleRegistry.reduce(
    (acc, entry) => {
      const category = entry.category || "utility";
      if (!acc[category]) acc[category] = [];
      acc[category].push(entry);
      return acc;
    },
    {} as Record<string, RegistryEntry[]>,
  );

  const marketplaceCategories = Object.keys(groupedRegistry).sort((a, b) =>
    (categoryLabels[a] || a).localeCompare(categoryLabels[b] || b),
  );

  const handleMarketplaceSort = (key: "name" | "category" | "author" | "added") => {
    setMarketplacePage(0);
    setMarketplaceSort((prev) => {
      if (prev.key === key) return { key, dir: prev.dir === "asc" ? "desc" : "asc" };
      // Newest-first is what someone clicking a date column is asking for;
      // the text columns still open A-Z.
      return { key, dir: key === "added" ? "desc" : "asc" };
    });
  };

  const handleInstalledSort = (key: "name" | "category" | "status") => {
    setInstalledSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );
  };

  const sortedInstalled = [...filteredInstalled].sort((a, b) => {
    let valA = "";
    let valB = "";
    if (installedSort.key === "name") {
      valA = a.name;
      valB = b.name;
    } else if (installedSort.key === "category") {
      valA = categoryLabels[a.category || "utility"] || a.category || "";
      valB = categoryLabels[b.category || "utility"] || b.category || "";
    } else if (installedSort.key === "status") {
      const statusRank = (p: PluginInfo) => (!p.enabled ? 2 : p.configured ? 0 : 1);
      return installedSort.dir === "asc" ? statusRank(a) - statusRank(b) : statusRank(b) - statusRank(a);
    }
    return installedSort.dir === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
  });

  const needsAttention = (plugin: PluginInfo) =>
    plugin.enabled &&
    plugin.plugin_type !== "output" &&
    plugin.plugin_type !== "transition" &&
    (!plugin.configured ||
      findOAuthConnection(connections?.connections, plugin.id)?.status === "reauthorization_required");
  const attentionPlugins = sortedInstalled.filter(needsAttention);
  const readyPlugins = sortedInstalled.filter((plugin) => !needsAttention(plugin));
  const currentSelectedId = sortedInstalled.some((plugin) => plugin.id === selectedId)
    ? selectedId
    : selectedId === ""
      ? ""
      : (oauthReturn?.pluginId ?? attentionPlugins[0]?.id ?? sortedInstalled[0]?.id);

  const updatesAvailableCount = (data?.plugins ?? []).filter((p) => p.update_available === true).length;

  // Git install dialog (shared, used in Marketplace tab)
  const gitInstallDialog = (
    <Dialog open={gitDialogOpen} onOpenChange={setGitDialogOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("gitInstallTitle")}</DialogTitle>
          <DialogDescription>{t("gitInstallDescription")}</DialogDescription>
        </DialogHeader>
        <Box className="py-2">
          <GitInstallFields install={gitInstall} idPrefix="git" />
        </Box>
        <DialogFooter>
          <Button variant="outline" onClick={() => setGitDialogOpen(false)} disabled={gitInstall.isInstalling}>
            {tCommon("cancel")}
          </Button>
          <Button onClick={handleInstallFromGit} disabled={gitInstall.isInstalling || !gitInstall.canInstall}>
            {gitInstall.isInstalling ? (
              <>
                <Spinner className="mr-2" label={null} />
                {t("installing")}
              </>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" />
                {t("installPlugin")}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  // The section (integrations.tsx) owns the card, the header and its "Check
  // for updates"; this is the body under it. The toolbar is no longer a direct
  // child of PageCard (Tabs wraps it), so it takes the block padding PageCard
  // would have given it itself.
  return (
    <>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        {/* PageToolbar via its children escape hatch, not its left/right slots:
            the search field has to take whatever track the tab strip leaves,
            and a flex split cannot express "fill the rest". The toolbar
            contributes only the inset, which is what puts this row on the
            content column with the page title above it. `mb-4` moves off the
            grid because PageToolbar already carries it. */}
        <PageToolbar className="mb-0 py-3">
          <Box
            className={
              activeTab === "marketplace"
                ? "grid grid-cols-1 gap-3 items-center md:grid-cols-[auto_minmax(12rem,1fr)_auto]"
                : "grid grid-cols-1 gap-3 items-center sm:grid-cols-[auto_minmax(0,1fr)_auto]"
            }
          >
            {/* A phone gets Figma's full-width pair, "Installed · 6 | Marketplace". */}
            <TabsList className={phone ? "grid w-full grid-cols-2" : "w-fit"}>
              <TabsTrigger value="installed">
                {t("tabInstalled")}
                {data &&
                  (phone ? (
                    ` · ${data.total}`
                  ) : (
                    <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 py-0 h-4">
                      {data.total}
                    </Badge>
                  ))}
              </TabsTrigger>
              <TabsTrigger value="marketplace">
                {t("tabMarketplace")}
                {!phone && availableCount > 0 && (
                  <Badge variant="outline" className="ml-1.5 text-[10px] px-1.5 py-0 h-4">
                    {availableCount}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>
            {!(phone && activeTab === "installed") && (
              <Box className="relative min-w-0 w-full">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                <Input
                  placeholder={
                    activeTab === "installed" ? t("searchInstalledPlaceholder") : t("searchAvailablePlaceholder")
                  }
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setMarketplacePage(0);
                  }}
                  aria-label={
                    activeTab === "installed" ? t("searchInstalledPlaceholder") : t("searchAvailablePlaceholder")
                  }
                  className="pl-9 w-full"
                />
              </Box>
            )}
            {/* Auto-update governs the installed plugins, so it rides with
                their tab: right of the search on a wide screen, a one-line row
                of its own under it on a phone. */}
            {activeTab === "installed" && !phone && <PluginAutoUpdateSwitch className="sm:justify-self-end" />}
            {activeTab === "marketplace" && (
              <Flex align="center" gap="2" className="shrink-0 md:justify-self-end">
                {!phone && !query && (
                  <Flex className="rounded-md border overflow-hidden">
                    <Button
                      variant={marketplaceView === "card" ? "secondary" : "ghost"}
                      size="icon"
                      className="h-9 w-9 rounded-none border-0"
                      onClick={() => setMarketplaceView("card")}
                      aria-label={t("cardViewAriaLabel")}
                      aria-pressed={marketplaceView === "card"}
                    >
                      <LayoutGrid className="h-4 w-4" />
                    </Button>
                    <Button
                      variant={marketplaceView === "list" ? "secondary" : "ghost"}
                      size="icon"
                      className="h-9 w-9 rounded-none border-0"
                      onClick={() => setMarketplaceView("list")}
                      aria-label={t("listViewAriaLabel")}
                      aria-pressed={marketplaceView === "list"}
                    >
                      <LayoutList className="h-4 w-4" />
                    </Button>
                  </Flex>
                )}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label={t("moreOptionsAriaLabel")}>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => setGitDialogOpen(true)}>
                      <GitBranch className="h-4 w-4 mr-2" />
                      {t("addFromGit")}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </Flex>
            )}
          </Box>
        </PageToolbar>

        <PageSection {...anchorProps("integrations.root")}>
          {/* ── Installed Tab ── */}
          <TabsContent value="installed" className="mt-0">
            {isLoading ? (
              <Box role="status" aria-label={tCommon("loading")} aria-busy="true">
                <Text className="sr-only">{tCommon("loading")}</Text>
                <ListRowGroup size="touch" aria-hidden="true">
                  {Array.from({ length: 5 }, (_, i) => (
                    <ListRow
                      key={i}
                      leading={<Skeleton className="h-8 w-8 rounded-md" />}
                      title={<Skeleton className="h-4 w-32 max-w-full" />}
                      description={<Skeleton className="h-3 w-20 max-w-full" />}
                    />
                  ))}
                </ListRowGroup>
              </Box>
            ) : error ? (
              <Card className="border-destructive">
                <CardContent className="flex items-center gap-3 py-6">
                  <AlertCircle className="h-5 w-5 text-destructive" />
                  <Text tone="destructive">
                    {t("loadPluginsError", { error: error instanceof Error ? error.message : tCommon("error") })}
                  </Text>
                </CardContent>
              </Card>
            ) : filteredInstalled.length === 0 ? (
              query ? (
                <EmptyState icon={Search} title={t("noInstalledMatch", { query: searchQuery })} className="py-16" />
              ) : (
                <EmptyState
                  icon={Puzzle}
                  title={t("noPluginsInstalled")}
                  description={t("headToMarketplace")}
                  action={
                    <Button variant="outline" onClick={() => setActiveTab("marketplace")}>
                      {t("browseMarketplace")}
                    </Button>
                  }
                  className="py-16"
                />
              )
            ) : (
              <Stack gap="3">
                {updatesAvailableCount > 0 && (
                  <Flex
                    align="center"
                    justify="between"
                    className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 dark:border-amber-800 dark:bg-amber-950/40"
                  >
                    <Text tone="warning">{t("pluginUpdatesAvailable", { count: updatesAvailableCount })}</Text>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 border-amber-300 text-amber-700 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-900"
                      onClick={handleUpdateAll}
                      disabled={isUpdatingAll || !!updatingId}
                    >
                      {isUpdatingAll ? (
                        <Spinner size="sm" className="mr-1.5" label={null} />
                      ) : (
                        <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                      )}
                      {isUpdatingAll ? t("updating") : t("updateAllCount", { count: updatesAvailableCount })}
                    </Button>
                  </Flex>
                )}
                {/* The groups already sort a phone's list by status (Figma 324:50158). */}
                {!phone && (
                  <Flex gap="3" wrap role="group" aria-label={t("sortInstalled")}>
                    {(["name", "category", "status"] as const).map((key) => (
                      <SortHeaderButton
                        key={key}
                        label={t(`${key}Column`)}
                        active={installedSort.key === key}
                        dir={installedSort.dir}
                        onSort={() => handleInstalledSort(key)}
                      />
                    ))}
                  </Flex>
                )}
                <Box className="grid items-start gap-5 md:grid-cols-[minmax(0,0.45fr)_minmax(0,0.55fr)] xl:grid-cols-[minmax(0,0.6fr)_minmax(0,0.4fr)]">
                  <Stack gap="4" className="min-w-0">
                    {[
                      { label: t("needsAttention"), plugins: attentionPlugins },
                      { label: t("tabInstalled"), plugins: readyPlugins },
                    ]
                      .filter((group) => group.plugins.length > 0)
                      .map((group) => (
                        <Stack gap="2" key={group.label}>
                          <Heading
                            level={2}
                            size="sm"
                            className="px-4 font-mono uppercase tracking-wide text-muted-foreground"
                          >
                            {group.label}
                          </Heading>
                          <ListRowGroup aria-label={group.label} size="touch">
                            {group.plugins.map((plugin) => (
                              <InstalledPluginRow
                                key={plugin.id}
                                plugin={plugin}
                                connection={findOAuthConnection(connections?.connections, plugin.id)}
                                desktop={desktop}
                                selected={currentSelectedId === plugin.id}
                                onSelect={setSelectedId}
                                detailTarget={detailTarget}
                                onToggle={handleToggle}
                                isToggling={toggleMutation.isPending}
                                onConfigUpdate={() => queryClient.invalidateQueries({ queryKey: ["plugins"] })}
                                onUninstall={handleUninstall}
                                onUpdate={handleUpdate}
                                isUninstalling={uninstallingId === plugin.id}
                                isUpdating={updatingId === plugin.id}
                                registryEntry={registryData?.entries.find(
                                  (entry) => entry.id === (plugin.base_plugin_id || plugin.id),
                                )}
                              />
                            ))}
                          </ListRowGroup>
                        </Stack>
                      ))}
                  </Stack>
                  {desktop && (
                    <Box as="aside" aria-label={t("integrationSettings")} ref={setDetailTarget} className="min-w-0" />
                  )}
                </Box>
                {phone && (
                  <Box as="section" aria-labelledby="plugin-updates-heading" className="grid gap-3 border-t pt-4">
                    <Heading
                      id="plugin-updates-heading"
                      level={2}
                      size="sm"
                      className="px-4 font-mono uppercase tracking-wide text-muted-foreground"
                    >
                      {t("pluginUpdatesSection")}
                    </Heading>
                    <Flex align="center" justify="between" gap="3" wrap className="px-4">
                      <PluginAutoUpdateSwitch />
                      <PluginUpdateCheckButton />
                    </Flex>
                  </Box>
                )}
              </Stack>
            )}
          </TabsContent>

          {/* ── Marketplace Tab ── */}
          <TabsContent value="marketplace" className="mt-0 space-y-4">
            <Flex align="center" justify="between" gap="3" wrap>
              <Text size="sm" tone="muted" role="status" aria-live="polite">
                {t("catalogCount", { count: filteredRegistry.length })}
              </Text>
              <Select
                value={categoryFilter}
                onValueChange={(value) => {
                  setCategoryFilter(value || "all");
                  setMarketplacePage(0);
                }}
              >
                <SelectTrigger className="w-full sm:w-48" aria-label={t("categoryFilter")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("allCategories")}</SelectItem>
                  {[...new Set(allRegistryEntries.map((entry) => entry.category || "utility"))]
                    .sort()
                    .map((category) => (
                      <SelectItem key={category} value={category}>
                        {categoryLabels[category] || category}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </Flex>
            {filteredRegistry.length === 0 ? (
              query ? (
                <EmptyState icon={Search} title={t("noPluginsMatch", { query: searchQuery })} className="py-16" />
              ) : (
                <EmptyState
                  icon={Puzzle}
                  title={t("noRegistryPluginsFound")}
                  description={t("canInstallCustomGitDescription")}
                  className="py-16"
                />
              )
            ) : marketplaceView === "card" && !phone && !query ? (
              <Stack gap="6" className="animate-card-fade-in">
                {(() => {
                  let globalIndex = 0;
                  return marketplaceCategories.map((category) => {
                    const entries = groupedRegistry[category] ?? [];
                    if (entries.length === 0) return null;
                    return (
                      <Box as="section" key={category}>
                        {/* The category colour lives on the section heading, not on
                          every card: the grid is grouped, so a badge per card would
                          repeat the heading verbatim N times. Cards in the public
                          directory carry it because that grid is flat. */}
                        <Heading level={2} size="sm" className="mb-3 flex items-center gap-2">
                          <PluginCategoryBadge category={category} label={categoryLabels[category] || category} />
                          <Text as="span" size="xs" tone="muted" className="normal-case tracking-normal">
                            ({entries.length})
                          </Text>
                        </Heading>
                        <Grid cols="1" md="2" gap="4" className="xl:grid-cols-3 items-stretch">
                          {entries.map((entry) => {
                            const cardIndex = globalIndex++;
                            return (
                              <RegistryPluginCard
                                key={entry.id}
                                entry={entry}
                                onInstall={handleInstall}
                                isInstalling={installingId === entry.id}
                                isInstalled={installedIds.has(entry.id)}
                                index={cardIndex}
                              />
                            );
                          })}
                        </Grid>
                      </Box>
                    );
                  });
                })()}
              </Stack>
            ) : (
              <Stack gap="3">
                <Flex gap="3" wrap role="group" aria-label={t("sortMarketplace")}>
                  {(["name", "category", "author", "added"] as const).map((key) => (
                    <SortHeaderButton
                      key={key}
                      label={t(`${key}Column`)}
                      active={marketplaceSort.key === key}
                      dir={marketplaceSort.dir}
                      onSort={() => handleMarketplaceSort(key)}
                    />
                  ))}
                </Flex>
                <Card className="overflow-hidden divide-y">
                  {visibleRegistry.map((entry) => (
                    <RegistryPluginCard
                      key={entry.id}
                      compact
                      entry={entry}
                      onInstall={handleInstall}
                      isInstalling={installingId === entry.id}
                      isInstalled={installedIds.has(entry.id)}
                    />
                  ))}
                </Card>
              </Stack>
            )}
            {resultPages > 1 && (
              <Flex align="center" justify="between" gap="2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={currentMarketplacePage === 0}
                  onClick={() => setMarketplacePage(currentMarketplacePage - 1)}
                >
                  {t("previousResults")}
                </Button>
                <Text size="sm">{t("resultsPage", { current: currentMarketplacePage + 1, total: resultPages })}</Text>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={currentMarketplacePage >= resultPages - 1}
                  onClick={() => setMarketplacePage(currentMarketplacePage + 1)}
                >
                  {t("nextResults")}
                </Button>
              </Flex>
            )}
          </TabsContent>
        </PageSection>
      </Tabs>

      {gitInstallDialog}
    </>
  );
}
